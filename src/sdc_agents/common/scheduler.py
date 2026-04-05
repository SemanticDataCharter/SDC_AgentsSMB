"""Pipeline scheduler for SDC Agents SMB.

Provides scheduled execution of agent tool pipelines using APScheduler.
Each pipeline step invokes an existing toolset tool with declared arguments.
All tool calls go through the existing AuditLogger.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from importlib import import_module
from typing import Any

from sdc_agents.common.audit import AuditLogger
from sdc_agents.common.config import SDCAgentsConfig, ScheduleJobConfig

logger = logging.getLogger("sdc_agents.scheduler")

AGENT_REGISTRY: dict[str, tuple[str, str]] = {
    "assembly": ("sdc_agents.toolsets.assembly", "AssemblyToolset"),
    "catalog": ("sdc_agents.toolsets.catalog", "CatalogToolset"),
    "distribution": ("sdc_agents.toolsets.distribution", "DistributionToolset"),
    "generator": ("sdc_agents.toolsets.generator", "GeneratorToolset"),
    "introspect": ("sdc_agents.toolsets.introspect", "IntrospectToolset"),
    "knowledge": ("sdc_agents.toolsets.knowledge", "KnowledgeToolset"),
    "mapping": ("sdc_agents.toolsets.mapping", "MappingToolset"),
    "validation": ("sdc_agents.toolsets.validation", "ValidationToolset"),
}


def _load_toolset(agent_name: str, config: SDCAgentsConfig):
    """Dynamically import and instantiate a toolset for the given agent."""
    if agent_name not in AGENT_REGISTRY:
        raise ValueError(
            f"Unknown agent '{agent_name}'. Valid: {', '.join(sorted(AGENT_REGISTRY))}"
        )
    module_path, class_name = AGENT_REGISTRY[agent_name]
    mod = import_module(module_path)
    cls = getattr(mod, class_name)
    return cls(config=config)


class PipelineRunner:
    """Executes a sequence of pipeline steps using existing toolsets."""

    def __init__(self, config: SDCAgentsConfig):
        self._config = config
        self._audit = AuditLogger(config.audit.path, config.audit.log_level)

    async def run_job(self, job_name: str, job: ScheduleJobConfig) -> dict:
        """Run all steps in a scheduled pipeline job sequentially.

        If a step fails, remaining steps are skipped. Sends notification
        on completion/failure if notify_on matches.

        Args:
            job_name: Name of the schedule job (for logging).
            job: The job configuration with steps and notify_on.

        Returns:
            Dict with job_name, steps_completed, steps_total, status,
            results, and errors.
        """
        start = time.monotonic()
        steps_completed = 0
        step_results: list[dict] = []
        errors: list[dict] = []
        status = "success"

        for i, step in enumerate(job.steps):
            step_start = time.monotonic()
            try:
                toolset = _load_toolset(step.agent, self._config)
                tools = await toolset.get_tools()

                # Find tool by name
                tool_func = None
                for t in tools:
                    if t.name == step.tool:
                        tool_func = t
                        break

                if tool_func is None:
                    raise ValueError(
                        f"Tool '{step.tool}' not found in agent '{step.agent}'. "
                        f"Available: {[t.name for t in tools]}"
                    )

                result = await tool_func.run_async(args=step.args, tool_context=None)
                step_results.append({
                    "step": i,
                    "agent": step.agent,
                    "tool": step.tool,
                    "status": "completed",
                    "duration_ms": round((time.monotonic() - step_start) * 1000, 2),
                })
                steps_completed += 1

            except Exception as exc:
                error_info = {
                    "step": i,
                    "agent": step.agent,
                    "tool": step.tool,
                    "error": str(exc),
                    "duration_ms": round((time.monotonic() - step_start) * 1000, 2),
                }
                errors.append(error_info)
                step_results.append({**error_info, "status": "failed"})
                status = "failed"
                logger.error(
                    "Schedule '%s' step %d failed (%s.%s): %s",
                    job_name, i, step.agent, step.tool, exc,
                )
                break  # Skip remaining steps

        total_duration = round((time.monotonic() - start) * 1000, 2)
        result = {
            "job_name": job_name,
            "steps_completed": steps_completed,
            "steps_total": len(job.steps),
            "status": status,
            "results": step_results,
            "errors": errors,
            "duration_ms": total_duration,
            "trigger": "scheduled",
        }

        self._audit.log(
            agent="scheduler",
            tool="run_job",
            inputs={"job_name": job_name, "steps": len(job.steps)},
            outputs=result,
            start_time=start,
        )

        # Send notification if configured
        should_notify = (
            "always" in job.notify_on
            or (status == "failed" and "error" in job.notify_on)
            or (status == "success" and "success" in job.notify_on)
        )

        if should_notify and self._config.notifications:
            from sdc_agents.common.notify import Notifier

            notifier = Notifier(self._config)
            await notifier.send(
                event=f"schedule_{status}",
                summary=(
                    f"Schedule '{job_name}': {steps_completed}/{len(job.steps)} steps "
                    f"{'completed' if status == 'success' else 'failed'}"
                ),
                details={
                    "agent": "scheduler",
                    "tool": "run_job",
                    "job_name": job_name,
                    "steps_completed": steps_completed,
                    "steps_total": len(job.steps),
                    "status": status,
                    "duration_ms": total_duration,
                },
            )

        return result


class SchedulerRuntime:
    """Runs scheduled pipeline jobs using APScheduler cron triggers."""

    def __init__(self, config: SDCAgentsConfig):
        self._config = config
        self._runner = PipelineRunner(config)

    def start(self) -> None:
        """Start the scheduler. Blocks until KeyboardInterrupt."""
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger

        if not self._config.schedules:
            logger.warning("No schedules configured. Nothing to run.")
            return

        scheduler = AsyncIOScheduler()

        for job_name, job_config in self._config.schedules.items():
            trigger = CronTrigger.from_crontab(job_config.cron)
            scheduler.add_job(
                self._run_job_wrapper,
                trigger=trigger,
                args=[job_name, job_config],
                id=job_name,
                name=f"sdc-agents: {job_name}",
            )
            logger.info(
                "Registered schedule '%s' [%s] (%d steps)",
                job_name, job_config.cron, len(job_config.steps),
            )

        scheduler.start()
        logger.info("Scheduler started with %d jobs. Ctrl+C to stop.", len(self._config.schedules))

        try:
            asyncio.get_event_loop().run_forever()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Scheduler stopped.")
            scheduler.shutdown()

    async def _run_job_wrapper(self, job_name: str, job_config: ScheduleJobConfig) -> None:
        """Wrapper to run a job within the scheduler's async context."""
        try:
            result = await self._runner.run_job(job_name, job_config)
            logger.info(
                "Schedule '%s' completed: %d/%d steps (%s)",
                job_name, result["steps_completed"], result["steps_total"], result["status"],
            )
        except Exception as exc:
            logger.error("Schedule '%s' raised unexpected error: %s", job_name, exc)

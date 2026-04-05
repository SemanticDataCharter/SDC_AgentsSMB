"""CLI entry point for sdc-agents (SMB Edition).

Provides subcommands for serving agents as MCP servers, inspecting
audit logs, displaying configuration info, and validating config files.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from importlib import import_module
from pathlib import Path

import click

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

_VALID_AGENTS = ", ".join(sorted(AGENT_REGISTRY))


def _load_toolset(agent_name: str, config):
    """Dynamically import and instantiate a toolset for the given agent."""
    module_path, class_name = AGENT_REGISTRY[agent_name]
    mod = import_module(module_path)
    cls = getattr(mod, class_name)
    return cls(config=config)


def _parse_duration(duration: str) -> timedelta:
    """Parse a duration string like '24h', '7d', '30m' into a timedelta."""
    match = re.fullmatch(r"(\d+)([hdm])", duration.strip().lower())
    if not match:
        raise click.BadParameter(
            f"Invalid duration '{duration}'. Use format like '24h', '7d', or '30m'."
        )
    value, unit = int(match.group(1)), match.group(2)
    if unit == "h":
        return timedelta(hours=value)
    if unit == "d":
        return timedelta(days=value)
    return timedelta(minutes=value)


@click.group()
@click.option(
    "--config",
    default=None,
    envvar="SDC_AGENTS_CONFIG",
    type=click.Path(),
    help="Path to sdc-agents.yaml config file.  [default: sdc-agents.yaml]",
)
@click.pass_context
def main(ctx: click.Context, config: str | None) -> None:
    """SDC Agents SMB — purpose-scoped ADK agents for SDC4 data operations (local LLM)."""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config or "sdc-agents.yaml"


# ---------------------------------------------------------------------------
# serve
# ---------------------------------------------------------------------------


@main.command()
@click.option(
    "--mcp",
    required=True,
    metavar="AGENT",
    help=f"Agent to serve as MCP server.  Valid: {_VALID_AGENTS}",
)
@click.pass_context
def serve(ctx: click.Context, mcp: str) -> None:
    """Start an agent toolset as an MCP stdio server."""
    if mcp not in AGENT_REGISTRY:
        raise click.ClickException(f"Unknown agent '{mcp}'. Valid agents: {_VALID_AGENTS}")

    from sdc_agents.common.config import load_config

    try:
        config = load_config(ctx.obj["config_path"])
    except (FileNotFoundError, KeyError) as exc:
        raise click.ClickException(str(exc)) from exc

    asyncio.run(_run_mcp_server(mcp, config))


async def _run_mcp_server(agent_name: str, config) -> None:
    """Set up and run an MCP stdio server for the given agent toolset."""
    from google.adk.tools.mcp_tool.conversion_utils import adk_to_mcp_tool_type
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import TextContent

    toolset = _load_toolset(agent_name, config)
    adk_tools = await toolset.get_tools()

    # Build lookup: MCP tool name -> ADK FunctionTool
    adk_by_name = {t.name: t for t in adk_tools}
    mcp_tools = [adk_to_mcp_tool_type(t) for t in adk_tools]

    server = Server(f"sdc-agents-{agent_name}")

    @server.list_tools()
    async def list_tools():
        return mcp_tools

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        if name not in adk_by_name:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
        func = adk_by_name[name]
        result = await func.run_async(args=arguments, tool_context=None)
        text = json.dumps(result, default=str) if not isinstance(result, str) else result
        return [TextContent(type="text", text=text)]

    click.echo(f"Serving {agent_name} agent via MCP stdio ({len(adk_tools)} tools)...")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


# ---------------------------------------------------------------------------
# audit
# ---------------------------------------------------------------------------


@main.group()
def audit() -> None:
    """Inspect the structured audit log."""


@audit.command("show")
@click.option("--agent", default=None, help="Filter by agent name.")
@click.option("--tool", default=None, help="Filter by tool name.")
@click.option(
    "--last", default=None, metavar="DURATION", help="Show records within duration (e.g. 24h, 7d)."
)
@click.option("--limit", default=50, show_default=True, help="Maximum records to display.")
@click.option(
    "--audit-path", default=None, type=click.Path(), help="Audit log path (overrides config)."
)
@click.pass_context
def audit_show(
    ctx: click.Context,
    agent: str | None,
    tool: str | None,
    last: str | None,
    limit: int,
    audit_path: str | None,
) -> None:
    """Display audit log records with optional filters."""
    # Resolve audit path
    log_path: str | None = audit_path
    if log_path is None:
        from sdc_agents.common.config import load_config

        try:
            config = load_config(ctx.obj["config_path"])
            log_path = config.audit.path
        except (FileNotFoundError, KeyError):
            log_path = ".sdc-cache/audit.jsonl"

    path = Path(log_path)
    if not path.exists():
        click.echo(f"No audit log found at {path}")
        return

    # Parse time filter
    cutoff: datetime | None = None
    if last is not None:
        try:
            delta = _parse_duration(last)
        except click.BadParameter as exc:
            raise click.ClickException(str(exc)) from exc
        cutoff = datetime.now(timezone.utc) - delta

    # Read and filter records
    records: list[dict] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue

        if agent and record.get("agent") != agent:
            continue
        if tool and record.get("tool") != tool:
            continue
        if cutoff:
            ts_str = record.get("timestamp", "")
            try:
                ts = datetime.fromisoformat(ts_str)
                if ts < cutoff:
                    continue
            except (ValueError, TypeError):
                continue

        records.append(record)

    if not records:
        click.echo("No matching audit records.")
        return

    # Display last N records
    for rec in records[-limit:]:
        click.echo("---")
        click.echo(f"  timestamp : {rec.get('timestamp', '?')}")
        click.echo(f"  agent     : {rec.get('agent', '?')}")
        click.echo(f"  tool      : {rec.get('tool', '?')}")
        click.echo(f"  duration  : {rec.get('duration_ms', '?')} ms")
        inputs = rec.get("inputs", {})
        if isinstance(inputs, dict):
            click.echo(f"  inputs    : {', '.join(inputs.keys()) or '(none)'}")
        else:
            click.echo(f"  inputs    : {inputs}")


@audit.command("serve")
@click.option("--port", default=8080, show_default=True, help="Port for the dashboard server.")
@click.option(
    "--audit-path", default=None, type=click.Path(), help="Audit log path (overrides config)."
)
@click.pass_context
def audit_serve(ctx: click.Context, port: int, audit_path: str | None) -> None:
    """Start the audit dashboard web UI."""
    try:
        import uvicorn
    except ImportError:
        raise click.ClickException(
            "uvicorn is required for the audit dashboard. "
            "Install with: pip install sdc-agents-smb[dashboard]"
        )

    from sdc_agents import dashboard

    # Resolve audit path
    if audit_path:
        dashboard._audit_path = audit_path
    else:
        from sdc_agents.common.config import load_config

        try:
            config = load_config(ctx.obj["config_path"])
            dashboard._audit_path = config.audit.path
        except (FileNotFoundError, KeyError):
            dashboard._audit_path = ".sdc-cache/audit.jsonl"

    click.echo(f"Audit dashboard: http://localhost:{port}")
    click.echo(f"Reading: {dashboard._audit_path}")
    uvicorn.run(dashboard.app, host="127.0.0.1", port=port, log_level="warning")


# ---------------------------------------------------------------------------
# info
# ---------------------------------------------------------------------------


@main.command()
@click.pass_context
def info(ctx: click.Context) -> None:
    """Display configuration summary and agent inventory."""
    from sdc_agents.common.config import load_config

    config_path = ctx.obj["config_path"]
    try:
        config = load_config(config_path)
    except (FileNotFoundError, KeyError) as exc:
        raise click.ClickException(f"Cannot load config: {exc}") from exc

    click.echo(f"Config      : {config_path}")
    click.echo(f"LLM model   : {config.model.default}")
    click.echo(f"Ollama URL  : {config.model.ollama_base_url}")
    click.echo(f"Cache root  : {config.cache.root}")
    click.echo(f"Output dir  : {config.output.directory}")
    click.echo(f"Audit path  : {config.audit.path}")
    click.echo(f"HITL review : {'enabled' if config.assembly.review_before_publish else 'disabled'}")
    click.echo(f"Notify chans: {len(config.notifications)}")
    click.echo(f"Schedules   : {len(config.schedules)}")
    click.echo()

    # Agent inventory with tool counts
    click.echo("Agents (8):")
    tool_counts = {
        "assembly": 7,
        "catalog": 7,
        "distribution": 5,
        "generator": 3,
        "introspect": "6+",  # Dynamic: +1 per installed ToolsetHub toolset
        "knowledge": 3,
        "mapping": 3,
        "validation": 3,
    }
    for name in sorted(AGENT_REGISTRY):
        count = tool_counts.get(name, "?")
        click.echo(f"  {name:16s} {count} tools")

    # Show installed ToolsetHub toolsets
    from sdc_agents.common.toolset_loader import ToolsetLoader

    loader = ToolsetLoader(config)
    toolsets = loader.discover_installed()
    installed = [t for t in toolsets if t.get("available")]
    if installed:
        click.echo(f"  + {len(installed)} ToolsetHub toolset(s) installed:")
        for t in installed:
            click.echo(f"    {t['name']:28s} {len(t.get('tools', []))} tools")
    else:
        click.echo("  + 0 ToolsetHub toolsets installed (3 available)")
    click.echo()

    # Datasources
    if config.datasources:
        click.echo(f"Datasources ({len(config.datasources)}):")
        for name, ds in config.datasources.items():
            click.echo(f"  {name:20s} type={ds.type}")
    else:
        click.echo("Datasources: (none)")
    click.echo()

    # Destinations
    if config.destinations:
        click.echo(f"Destinations ({len(config.destinations)}):")
        for name, dest in config.destinations.items():
            endpoint = dest.endpoint or dest.path or ""
            click.echo(f"  {name:20s} type={dest.type}  endpoint={endpoint}")
    else:
        click.echo("Destinations: (none)")


# ---------------------------------------------------------------------------
# validate-config
# ---------------------------------------------------------------------------


@main.command("validate-config")
@click.pass_context
def validate_config(ctx: click.Context) -> None:
    """Validate the configuration file and report errors."""
    from pydantic import ValidationError

    from sdc_agents.common.config import load_config

    config_path = ctx.obj["config_path"]
    try:
        load_config(config_path)
    except FileNotFoundError:
        click.echo(f"Error: config file not found: {config_path}", err=True)
        sys.exit(1)
    except KeyError as exc:
        click.echo(f"Error: missing environment variable: {exc}", err=True)
        sys.exit(1)
    except ValidationError as exc:
        click.echo(f"Error: config validation failed:\n{exc}", err=True)
        sys.exit(1)
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    click.echo(f"Config OK: {config_path}")


# ---------------------------------------------------------------------------
# assembly
# ---------------------------------------------------------------------------


@main.group()
def assembly() -> None:
    """Manage assembly review manifests and pending tasks."""


@assembly.command("list-pending")
@click.pass_context
def assembly_list_pending(ctx: click.Context) -> None:
    """List pending assembly review manifests and deferred tasks."""
    from sdc_agents.common.config import load_config

    try:
        config = load_config(ctx.obj["config_path"])
    except (FileNotFoundError, KeyError):
        config = None

    cache_root = config.cache.root if config else ".sdc-cache"
    pending_dir = Path(cache_root) / "pending"

    if not pending_dir.is_dir():
        click.echo("No pending directory found.")
        return

    manifests = sorted(pending_dir.glob("*.json"))
    if not manifests:
        click.echo("No pending manifests.")
        return

    for path in manifests:
        try:
            data = json.loads(path.read_text())
            status = data.get("status", "unknown")
            name = data.get("name", data.get("task_id", path.stem))
            title = data.get("title", "")
            created = data.get("created", data.get("submitted", ""))
            summary = data.get("summary", {})

            click.echo(f"  {name:30s} status={status:16s} created={created}")
            if title:
                click.echo(f"    title: {title}")
            if summary:
                reuse = summary.get("reuse_count", 0)
                mint = summary.get("mint_count", 0)
                cost = summary.get("estimated_cost", 0)
                click.echo(f"    reuse: {reuse}, mint: {mint}, est. cost: ${cost:.2f}")
        except (json.JSONDecodeError, KeyError):
            click.echo(f"  {path.stem:30s} (unreadable)")


@assembly.command("review")
@click.argument("name")
@click.pass_context
def assembly_review(ctx: click.Context, name: str) -> None:
    """Display details of a pending assembly review manifest."""
    from sdc_agents.common.config import load_config

    try:
        config = load_config(ctx.obj["config_path"])
    except (FileNotFoundError, KeyError):
        config = None

    cache_root = config.cache.root if config else ".sdc-cache"
    manifest_path = Path(cache_root) / "pending" / f"{name}.json"

    if not manifest_path.is_file():
        raise click.ClickException(f"No manifest found: {name}")

    manifest = json.loads(manifest_path.read_text())

    click.echo(f"Assembly Review: {manifest.get('title', name)}")
    click.echo(f"  Status  : {manifest.get('status', '?')}")
    click.echo(f"  Created : {manifest.get('created', '?')}")
    click.echo()

    summary = manifest.get("summary", {})
    click.echo(f"  Reuse components : {summary.get('reuse_count', 0)} (free)")
    click.echo(f"  Mint components  : {summary.get('mint_count', 0)} (billable)")
    click.echo(f"  Estimated cost   : ${summary.get('estimated_cost', 0):.2f}")
    click.echo(f"  Wallet balance   : ${summary.get('wallet_balance', 0):.2f}")
    click.echo()

    # Show components to mint
    mint_comps = manifest.get("mint_components", [])
    if mint_comps:
        click.echo("  Components to mint:")
        for comp in mint_comps:
            label = comp.get("label", "?")
            dtype = comp.get("data_type", "?")
            click.echo(f"    - {label} ({dtype})")
    click.echo()

    # Show reused components
    reused = manifest.get("reused_components", [])
    if reused:
        click.echo(f"  Components reused ({len(reused)}):")
        for comp in reused[:10]:  # Show first 10
            label = comp.get("label", "?")
            ct_id = comp.get("ct_id", "?")
            click.echo(f"    - {label} [{ct_id}]")
        if len(reused) > 10:
            click.echo(f"    ... and {len(reused) - 10} more")

    click.echo()
    click.echo(f"  To approve: sdc-agents assembly approve {name}")
    click.echo(f"  To reject:  sdc-agents assembly reject {name}")


@assembly.command("approve")
@click.argument("name")
@click.pass_context
def assembly_approve(ctx: click.Context, name: str) -> None:
    """Approve a pending assembly manifest and submit to the Assembly API."""
    from sdc_agents.common.config import load_config

    try:
        config = load_config(ctx.obj["config_path"])
    except (FileNotFoundError, KeyError) as exc:
        raise click.ClickException(str(exc)) from exc

    cache_root = config.cache.root
    manifest_path = Path(cache_root) / "pending" / f"{name}.json"

    if not manifest_path.is_file():
        raise click.ClickException(f"No manifest found: {name}")

    manifest = json.loads(manifest_path.read_text())

    if manifest.get("status") != "pending_review":
        raise click.ClickException(
            f"Manifest '{name}' has status '{manifest.get('status')}', not 'pending_review'."
        )

    # Update status to approved
    manifest["status"] = "approved"
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str))

    click.echo(f"Approved: {name}")
    click.echo("Submitting to Assembly API...")

    # Submit via toolset
    toolset = _load_toolset("assembly", config)
    try:
        result = asyncio.run(toolset.submit_approved_assembly(name))
        mode = result.get("mode", "?")
        if mode == "sync":
            click.echo(f"  Published: {result.get('dm_ct_id', '?')}")
            click.echo(f"  Download:  sdc-agents serve --mcp catalog")
        elif mode == "async":
            task_id = result.get("task_id", "?")
            click.echo(f"  Submitted (async): task_id={task_id}")
            click.echo(f"  Estimated cost: ${result.get('estimated_cost', 0):.2f}")
        else:
            click.echo(f"  Result: {json.dumps(result, default=str)}")
    except Exception as exc:
        # Revert status on failure
        manifest["status"] = "pending_review"
        manifest_path.write_text(json.dumps(manifest, indent=2, default=str))
        raise click.ClickException(f"Assembly failed: {exc}") from exc


@assembly.command("reject")
@click.argument("name")
@click.pass_context
def assembly_reject(ctx: click.Context, name: str) -> None:
    """Reject and remove a pending assembly manifest."""
    from sdc_agents.common.config import load_config

    try:
        config = load_config(ctx.obj["config_path"])
    except (FileNotFoundError, KeyError):
        config = None

    cache_root = config.cache.root if config else ".sdc-cache"
    manifest_path = Path(cache_root) / "pending" / f"{name}.json"

    if not manifest_path.is_file():
        raise click.ClickException(f"No manifest found: {name}")

    manifest = json.loads(manifest_path.read_text())
    manifest["status"] = "rejected"
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str))

    click.echo(f"Rejected: {name}")


# ---------------------------------------------------------------------------
# schedule
# ---------------------------------------------------------------------------


@main.group()
def schedule() -> None:
    """Manage scheduled pipeline jobs."""


@schedule.command("list")
@click.pass_context
def schedule_list(ctx: click.Context) -> None:
    """List configured schedule jobs with cron expressions."""
    from sdc_agents.common.config import load_config

    try:
        config = load_config(ctx.obj["config_path"])
    except (FileNotFoundError, KeyError) as exc:
        raise click.ClickException(str(exc)) from exc

    if not config.schedules:
        click.echo("No schedules configured.")
        return

    click.echo(f"Schedules ({len(config.schedules)}):")
    for name, job in config.schedules.items():
        notify = ", ".join(job.notify_on)
        click.echo(f"  {name:30s} cron={job.cron:20s} steps={len(job.steps)}  notify={notify}")
        for i, step in enumerate(job.steps):
            args_str = ", ".join(f"{k}={v}" for k, v in step.args.items()) if step.args else ""
            click.echo(f"    {i}: {step.agent}.{step.tool}({args_str})")


@schedule.command("run")
@click.pass_context
def schedule_run(ctx: click.Context) -> None:
    """Start the scheduler (foreground process, Ctrl+C to stop)."""
    import logging

    from sdc_agents.common.config import load_config
    from sdc_agents.common.scheduler import SchedulerRuntime

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    try:
        config = load_config(ctx.obj["config_path"])
    except (FileNotFoundError, KeyError) as exc:
        raise click.ClickException(str(exc)) from exc

    if not config.schedules:
        raise click.ClickException(
            "No schedules configured. Add a 'schedules' section to your config."
        )

    runtime = SchedulerRuntime(config)
    runtime.start()


@schedule.command("trigger")
@click.argument("job_name")
@click.pass_context
def schedule_trigger(ctx: click.Context, job_name: str) -> None:
    """Run a schedule job immediately (for testing)."""
    from sdc_agents.common.config import load_config
    from sdc_agents.common.scheduler import PipelineRunner

    try:
        config = load_config(ctx.obj["config_path"])
    except (FileNotFoundError, KeyError) as exc:
        raise click.ClickException(str(exc)) from exc

    if job_name not in config.schedules:
        available = ", ".join(sorted(config.schedules.keys())) or "(none)"
        raise click.ClickException(
            f"Unknown schedule '{job_name}'. Available: {available}"
        )

    job = config.schedules[job_name]
    runner = PipelineRunner(config)

    click.echo(f"Triggering '{job_name}' ({len(job.steps)} steps)...")
    result = asyncio.run(runner.run_job(job_name, job))

    status = result["status"]
    completed = result["steps_completed"]
    total = result["steps_total"]
    duration = result["duration_ms"]

    click.echo(f"  Status: {status}")
    click.echo(f"  Steps:  {completed}/{total} completed")
    click.echo(f"  Duration: {duration:.0f} ms")

    if result["errors"]:
        click.echo("  Errors:")
        for err in result["errors"]:
            click.echo(f"    step {err['step']} ({err['agent']}.{err['tool']}): {err['error']}")


# ---------------------------------------------------------------------------
# pipeline
# ---------------------------------------------------------------------------


@main.group()
def pipeline() -> None:
    """Run pre-built pipeline templates."""


@pipeline.command("list")
def pipeline_list() -> None:
    """List available pipeline templates."""
    from sdc_agents.common.pipeline import list_templates

    templates = list_templates()
    if not templates:
        click.echo("No pipeline templates found.")
        return

    click.echo(f"Pipeline templates ({len(templates)}):")
    for t in templates:
        params = ", ".join(t["parameters"]) if t["parameters"] else "(none)"
        click.echo(f"  {t['name']:24s} {t['step_count']} steps  params: {params}")
        if t["description"]:
            click.echo(f"    {t['description']}")


@pipeline.command("show")
@click.argument("name")
def pipeline_show(name: str) -> None:
    """Show details of a pipeline template."""
    from sdc_agents.common.pipeline import load_template

    try:
        template = load_template(name)
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(f"Pipeline: {template.get('name', name)}")
    click.echo(f"  {template.get('description', '')}")
    click.echo()

    params = template.get("parameters", [])
    if params:
        click.echo("Parameters:")
        for p in params:
            req = " (required)" if p.get("required") else ""
            click.echo(f"  --{p['name']:20s} {p.get('description', '')}{req}")
        click.echo()

    click.echo("Steps:")
    for i, step in enumerate(template.get("steps", [])):
        args_str = ", ".join(f"{k}={v}" for k, v in step.get("args", {}).items())
        click.echo(f"  {i}: {step['agent']}.{step['tool']}({args_str})")


@pipeline.command("run")
@click.argument("name")
@click.option("--param", "-p", multiple=True, help="Parameter as key=value (repeatable).")
@click.pass_context
def pipeline_run(ctx: click.Context, name: str, param: tuple[str, ...]) -> None:
    """Run a pipeline template with the given parameters."""
    from sdc_agents.common.config import load_config
    from sdc_agents.common.pipeline import build_job_from_template
    from sdc_agents.common.scheduler import PipelineRunner

    # Parse key=value params
    params: dict[str, str] = {}
    for p in param:
        if "=" not in p:
            raise click.ClickException(f"Invalid parameter format: '{p}'. Use key=value.")
        key, value = p.split("=", 1)
        params[key] = value

    try:
        config = load_config(ctx.obj["config_path"])
    except (FileNotFoundError, KeyError) as exc:
        raise click.ClickException(str(exc)) from exc

    try:
        job = build_job_from_template(name, params)
    except (FileNotFoundError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(f"Running pipeline '{name}' ({len(job.steps)} steps)...")
    runner = PipelineRunner(config)
    result = asyncio.run(runner.run_job(f"pipeline:{name}", job))

    click.echo(f"  Status: {result['status']}")
    click.echo(f"  Steps:  {result['steps_completed']}/{result['steps_total']} completed")
    click.echo(f"  Duration: {result['duration_ms']:.0f} ms")

    if result["errors"]:
        click.echo("  Errors:")
        for err in result["errors"]:
            click.echo(f"    step {err['step']} ({err['agent']}.{err['tool']}): {err['error']}")


# ---------------------------------------------------------------------------
# compliance
# ---------------------------------------------------------------------------


@main.group()
def compliance() -> None:
    """Generate compliance reports from audit and lineage logs."""


@compliance.command("report")
@click.option("--format", "fmt", default="json", type=click.Choice(["json", "markdown", "html"]),
              help="Output format.")
@click.option("--last", default=None, metavar="DURATION",
              help="Include records from duration (e.g., 24h, 7d, 30d).")
@click.option("--output", "-o", default=None, type=click.Path(),
              help="Write report to file (default: stdout).")
@click.pass_context
def compliance_report(
    ctx: click.Context,
    fmt: str,
    last: str | None,
    output: str | None,
) -> None:
    """Generate a compliance report from audit and lineage logs."""
    from sdc_agents.common.compliance import ComplianceReporter
    from sdc_agents.common.config import load_config

    try:
        config = load_config(ctx.obj["config_path"])
        audit_path = config.audit.path
        cache_root = config.cache.root
    except (FileNotFoundError, KeyError):
        audit_path = ".sdc-cache/audit.jsonl"
        cache_root = ".sdc-cache"

    lineage_path = Path(cache_root) / "lineage.jsonl"

    # Parse duration
    last_hours = None
    last_days = None
    if last:
        try:
            delta = _parse_duration(last)
            total_hours = delta.total_seconds() / 3600
            if total_hours >= 24:
                last_days = int(total_hours / 24)
            else:
                last_hours = int(total_hours)
        except click.BadParameter as exc:
            raise click.ClickException(str(exc)) from exc

    reporter = ComplianceReporter(audit_path=audit_path, lineage_path=lineage_path)
    content = reporter.generate(
        last_hours=last_hours,
        last_days=last_days,
        output_format=fmt,
    )

    if output:
        Path(output).write_text(content)
        click.echo(f"Report written to: {output}")
    else:
        click.echo(content)


# ---------------------------------------------------------------------------
# toolset
# ---------------------------------------------------------------------------


@main.group()
def toolset() -> None:
    """Manage ToolsetHub toolsets (SMB datasource plugins)."""


@toolset.command("list")
@click.pass_context
def toolset_list(ctx: click.Context) -> None:
    """List available and installed ToolsetHub toolsets."""
    from sdc_agents.common.config import load_config
    from sdc_agents.common.toolset_loader import ToolsetLoader

    try:
        config = load_config(ctx.obj["config_path"])
    except (FileNotFoundError, KeyError):
        from sdc_agents.common.config import SDCAgentsConfig

        config = SDCAgentsConfig()

    loader = ToolsetLoader(config)
    toolsets = loader.discover_installed()

    if not toolsets:
        click.echo("No toolsets found.")
        return

    click.echo(f"ToolsetHub toolsets ({len(toolsets)}):")
    for t in toolsets:
        status = t.get("status", "?")
        security = t.get("security", {})
        hosts = ", ".join(security.get("network_hosts", []))
        click.echo(f"  {t['name']:28s} {status}")
        click.echo(f"    {t.get('description', '')}")
        click.echo(f"    network: {hosts}  read-only: {not security.get('file_write', False)}")


@toolset.command("info")
@click.argument("name")
@click.pass_context
def toolset_info(ctx: click.Context, name: str) -> None:
    """Show details of a ToolsetHub toolset."""
    from sdc_agents.common.config import load_config
    from sdc_agents.common.toolset_loader import ToolsetLoader

    try:
        config = load_config(ctx.obj["config_path"])
    except (FileNotFoundError, KeyError):
        from sdc_agents.common.config import SDCAgentsConfig

        config = SDCAgentsConfig()

    loader = ToolsetLoader(config)
    toolsets = loader.discover_installed()

    found = None
    for t in toolsets:
        if t["name"] == name:
            found = t
            break

    if not found:
        available = [t["name"] for t in toolsets]
        raise click.ClickException(
            f"Toolset '{name}' not found. Available: {', '.join(available)}"
        )

    click.echo(f"Toolset: {found['name']} v{found.get('version', '?')}")
    click.echo(f"  Author:      {found.get('author', '?')}")
    click.echo(f"  Description: {found.get('description', '')}")
    click.echo(f"  Status:      {found.get('status', '?')}")
    click.echo()

    security = found.get("security", {})
    click.echo("  Security Scope:")
    click.echo(f"    Network access:  {security.get('network_access', False)}")
    click.echo(f"    Network hosts:   {', '.join(security.get('network_hosts', []))}")
    click.echo(f"    Datasource types: {', '.join(security.get('datasource_types', []))}")
    click.echo(f"    File write:      {security.get('file_write', False)}")
    click.echo(f"    Audit compliant: {security.get('audit_compliant', False)}")
    click.echo()

    tools = found.get("tools", [])
    if tools:
        click.echo(f"  Tools ({len(tools)}):")
        for tool in tools:
            click.echo(f"    - {tool['name']}: {tool.get('description', '')}")

    deps = found.get("dependencies", [])
    if deps:
        click.echo(f"  Dependencies: {', '.join(deps)}")
        extra = found.get("install_extra", name)
        click.echo(f"  Install: pip install sdc-agents-smb[{extra}]")

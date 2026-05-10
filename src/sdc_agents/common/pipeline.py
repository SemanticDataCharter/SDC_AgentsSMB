"""Pipeline template loader and executor for SDC Agents SMB.

Loads YAML pipeline templates with {{ parameter }} substitution,
then executes them using the PipelineRunner from the scheduler module.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from sdc_agents.common.config import PipelineStep, ScheduleJobConfig

_TEMPLATE_VAR_PATTERN = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def _substitute_template_vars(obj: object, params: dict[str, str]) -> object:
    """Recursively substitute {{ var }} placeholders in strings."""
    if isinstance(obj, str):

        def _replace(match: re.Match) -> str:
            var_name = match.group(1)
            if var_name not in params:
                raise ValueError(
                    f"Missing template parameter '{var_name}'. "
                    f"Available: {list(params.keys())}"
                )
            return params[var_name]

        return _TEMPLATE_VAR_PATTERN.sub(_replace, obj)
    if isinstance(obj, dict):
        return {k: _substitute_template_vars(v, params) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_substitute_template_vars(item, params) for item in obj]
    return obj


def list_templates() -> list[dict]:
    """List all available pipeline templates (bundled + custom).

    Returns:
        List of dicts with name, description, parameters, and step_count.
    """
    templates = []

    # Bundled templates from the package
    template_dir = Path(__file__).parent.parent / "templates"
    if template_dir.is_dir():
        for path in sorted(template_dir.glob("*.yaml")):
            try:
                data = yaml.safe_load(path.read_text())
                templates.append(
                    {
                        "name": path.stem,
                        "description": data.get("description", ""),
                        "parameters": [p.get("name") for p in data.get("parameters", [])],
                        "step_count": len(data.get("steps", [])),
                        "source": "bundled",
                    }
                )
            except (yaml.YAMLError, KeyError):
                continue

    return templates


def load_template(name: str) -> dict:
    """Load a pipeline template by name.

    Searches bundled templates first, then custom template directories.

    Args:
        name: Template name (without .yaml extension).

    Returns:
        Parsed template dict with name, description, parameters, and steps.

    Raises:
        FileNotFoundError: If template not found.
    """
    # Search bundled templates
    template_dir = Path(__file__).parent.parent / "templates"
    template_path = template_dir / f"{name}.yaml"

    if not template_path.is_file():
        available = [t["name"] for t in list_templates()]
        raise FileNotFoundError(
            f"Template '{name}' not found. Available: {', '.join(available) or '(none)'}"
        )

    data = yaml.safe_load(template_path.read_text())
    return data


def build_job_from_template(
    template_name: str,
    params: dict[str, str],
) -> ScheduleJobConfig:
    """Load a template and build a ScheduleJobConfig with substituted parameters.

    Args:
        template_name: Name of the template.
        params: Parameter values to substitute (e.g., {"datasource": "my_csv"}).

    Returns:
        A ScheduleJobConfig ready to execute via PipelineRunner.

    Raises:
        FileNotFoundError: If template not found.
        ValueError: If required parameters are missing.
    """
    template = load_template(template_name)

    # Validate required parameters
    for param_def in template.get("parameters", []):
        if param_def.get("required", False) and param_def["name"] not in params:
            raise ValueError(
                f"Template '{template_name}' requires parameter '{param_def['name']}': "
                f"{param_def.get('description', '')}"
            )

    # Substitute parameters in steps
    raw_steps = template.get("steps", [])
    substituted_steps = _substitute_template_vars(raw_steps, params)

    steps = [PipelineStep(**step) for step in substituted_steps]
    return ScheduleJobConfig(
        cron="* * * * *",  # Placeholder — not used for immediate execution
        steps=steps,
        notify_on=["always"],
    )

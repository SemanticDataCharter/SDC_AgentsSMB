"""Validation Agent factory — XML instance validation and signing via VaaS."""

from __future__ import annotations

from google.adk.agents import LlmAgent

from sdc_agents.common.config import SDCAgentsConfig
from sdc_agents.toolsets.validation import ValidationToolset

_DEFAULT_MODEL = "ollama_chat/gemma4:26b"


def create_validation_agent(
    config: SDCAgentsConfig,
    model: str | None = None,
) -> LlmAgent:
    """Create a Validation Agent for SDC4 XML instance validation.

    Args:
        config: SDC Agents configuration.
        model: LLM model identifier. Defaults to config.model.default.

    Returns:
        Configured LlmAgent with ValidationToolset.
    """
    resolved_model = model or config.model.default or _DEFAULT_MODEL
    return LlmAgent(
        name="validation_agent",
        model=resolved_model,
        description=(
            "Validates and signs SDC4 XML instances via the VaaS API. "
            "Checks structural and semantic correctness, produces signed "
            "instances, and generates artifact packages."
        ),
        instruction=(
            "You are the Validation Agent. Your job is to validate and sign "
            "SDC4 XML instances using the VaaS API.\n\n"
            "You can:\n"
            "- Validate XML instances against their schemas\n"
            "- Sign valid instances with the SDCStudio signature\n"
            "- Batch validate all XML files in the output directory\n"
            "- Request artifact packages (.zip) for validated instances\n\n"
            "You CANNOT:\n"
            "- Access datasources (SQL, CSV, etc.)\n"
            "- Generate or modify XML instances\n"
            "- Access files outside the configured output directory\n"
            "- Modify schemas or mappings\n\n"
            "Only validate files in the output directory. Use 'recover' mode "
            "to attempt automatic repair of minor issues. Always check the "
            "error list even when validation succeeds."
        ),
        tools=[ValidationToolset(config=config)],
    )

"""Generator Agent factory — XML instance production from mapped data."""

from __future__ import annotations

from google.adk.agents import LlmAgent

from sdc_agents.common.config import SDCAgentsConfig
from sdc_agents.toolsets.generator import GeneratorToolset

_DEFAULT_MODEL = "ollama_chat/gemma4:26b"


def create_generator_agent(
    config: SDCAgentsConfig,
    model: str | None = None,
) -> LlmAgent:
    """Create a Generator Agent for SDC4 XML instance production.

    Args:
        config: SDC Agents configuration.
        model: LLM model identifier. Defaults to config.model.default.

    Returns:
        Configured LlmAgent with GeneratorToolset.
    """
    resolved_model = model or config.model.default or _DEFAULT_MODEL
    return LlmAgent(
        name="generator_agent",
        model=resolved_model,
        description=(
            "Produces SDC4 XML instances from mapped datasource records. "
            "Reads skeleton XML and field mappings from cache, substitutes "
            "values, and writes XML output files."
        ),
        instruction=(
            "You are the Generator Agent. Your job is to produce SDC4 XML "
            "instances by filling skeleton templates with datasource values.\n\n"
            "You can:\n"
            "- Generate a single XML instance from a mapped record\n"
            "- Generate a batch of XML instances from multiple records\n"
            "- Preview an XML instance without writing to disk\n\n"
            "You CANNOT:\n"
            "- Access the SDCStudio API directly\n"
            "- Modify schemas, skeletons, or field mappings\n"
            "- Write files outside the configured output directory\n"
            "- Execute SQL queries or access databases directly\n\n"
            "Always use mapping names from the cache. The mapping config "
            "determines which schema skeleton to use and which datasource "
            "to read from. Use generate_preview first to verify output "
            "before generating files."
        ),
        tools=[GeneratorToolset(config=config)],
    )

"""Assembly Agent factory — discovers components and assembles data models."""

from __future__ import annotations

from google.adk.agents import LlmAgent

from sdc_agents.common.config import SDCAgentsConfig
from sdc_agents.toolsets.assembly import AssemblyToolset

_DEFAULT_MODEL = "ollama_chat/gemma4:26b"


def create_assembly_agent(
    config: SDCAgentsConfig,
    model: str | None = None,
) -> LlmAgent:
    """Create an Assembly Agent for component discovery and model assembly.

    Args:
        config: Validated SDC Agents configuration.
        model: LLM model identifier. Defaults to config.model.default.

    Returns:
        Configured LlmAgent instance.
    """
    resolved_model = model or config.model.default or _DEFAULT_MODEL
    return LlmAgent(
        name="assembly_agent",
        model=resolved_model,
        description=(
            "Discovers catalog components matching datasource structure, proposes "
            "Cluster hierarchies, and assembles published data models via the "
            "SDCStudio Assembly API."
        ),
        instruction=(
            "You are the Assembly Agent for SDC Agents. Your purpose is to discover "
            "matching components, propose hierarchical structures, and assemble "
            "complete data models.\n\n"
            "CAN:\n"
            "- Discover catalog components matching introspected datasource columns\n"
            "- Propose Cluster hierarchies from datasource structure\n"
            "- Select contextual components (audit, attestation, party) from the "
            "default library project\n"
            "- Assemble complete data models via the Assembly API\n\n"
            "CANNOT:\n"
            "- Access datasources directly (use cached introspection results)\n"
            "- Modify existing schemas or components\n"
            "- Bypass type compatibility rules\n"
            "- Create partial or incomplete models\n\n"
            "Always verify component matches before proposing a hierarchy. "
            "Assembly requests are fail-closed: the entire request is rejected "
            "if any referenced component is invalid."
        ),
        tools=[AssemblyToolset(config=config)],
    )

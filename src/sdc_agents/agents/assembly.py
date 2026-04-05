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
            "- Verify that the Modeler's default project is private (verify_project_scope)\n"
            "- Discover catalog components matching introspected datasource columns\n"
            "- Propose Cluster hierarchies from datasource structure\n"
            "- Select contextual components (audit, attestation, party) from the "
            "default library project\n"
            "- Assemble complete data models via the Assembly API\n"
            "- Submit previously approved assembly manifests (submit_approved_assembly)\n"
            "- Poll async assembly tasks until completion (poll_assembly_task)\n\n"
            "WORKFLOW:\n"
            "1. verify_project_scope — ensures private project (called automatically)\n"
            "2. discover_components — find matching catalog components\n"
            "3. propose_cluster_hierarchy — build assembly tree\n"
            "4. assemble_model — if minting needed and review enabled, writes a review\n"
            "   manifest for user approval instead of calling the API directly\n"
            "5. After user approval: submit_approved_assembly submits the manifest\n"
            "6. For async results (HTTP 202): poll_assembly_task waits for completion\n"
            "7. Use the Catalog Agent's download_package tool to get the final ZIP\n\n"
            "CANNOT:\n"
            "- Access datasources directly (use cached introspection results)\n"
            "- Modify existing schemas or components\n"
            "- Bypass type compatibility rules\n"
            "- Create components in public projects\n"
            "- Create partial or incomplete models\n\n"
            "Always verify component matches before proposing a hierarchy. "
            "Assembly requests are fail-closed: the entire request is rejected "
            "if any referenced component is invalid."
        ),
        tools=[AssemblyToolset(config=config)],
    )

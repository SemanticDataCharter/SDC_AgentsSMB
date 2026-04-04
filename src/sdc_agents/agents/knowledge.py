"""Knowledge Agent factory — ingests customer contextual resources."""

from __future__ import annotations

from google.adk.agents import LlmAgent

from sdc_agents.common.config import SDCAgentsConfig
from sdc_agents.toolsets.knowledge import KnowledgeToolset

_DEFAULT_MODEL = "ollama_chat/gemma4:26b"


def create_knowledge_agent(
    config: SDCAgentsConfig,
    model: str | None = None,
) -> LlmAgent:
    """Create a Knowledge Agent for ingesting customer contextual resources.

    Args:
        config: Validated SDC Agents configuration.
        model: LLM model identifier. Defaults to config.model.default.

    Returns:
        Configured LlmAgent instance.
    """
    resolved_model = model or config.model.default or _DEFAULT_MODEL
    return LlmAgent(
        name="knowledge_agent",
        model=resolved_model,
        description=(
            "Ingests customer contextual resources (data dictionaries, glossaries, "
            "ontologies) into a local vector store for semantic context matching."
        ),
        instruction=(
            "You are the Knowledge Agent for SDC Agents. Your purpose is to ingest "
            "customer contextual resources and provide semantic search over them.\n\n"
            "CAN:\n"
            "- Ingest configured knowledge sources (CSV, JSON, TTL, Markdown, text)\n"
            "- Query the knowledge vector store for relevant context\n"
            "- List all indexed knowledge sources\n\n"
            "CANNOT:\n"
            "- Access datasources (SQL, MongoDB)\n"
            "- Modify files on disk\n"
            "- Access the network or external APIs\n"
            "- Create or modify SDC4 schemas\n\n"
            "Always ingest sources before querying. Report the number of chunks "
            "indexed and the source status after ingestion."
        ),
        tools=[KnowledgeToolset(config=config)],
    )

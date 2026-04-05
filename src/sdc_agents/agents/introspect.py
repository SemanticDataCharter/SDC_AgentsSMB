"""Introspect Agent factory — datasource structure extraction."""

from __future__ import annotations

from google.adk.agents import LlmAgent

from sdc_agents.common.config import SDCAgentsConfig
from sdc_agents.toolsets.introspect import IntrospectToolset

_DEFAULT_MODEL = "ollama_chat/gemma4:26b"


def create_introspect_agent(
    config: SDCAgentsConfig,
    model: str | None = None,
) -> LlmAgent:
    """Create an Introspect Agent for datasource structure discovery.

    The agent can execute read-only SQL queries, introspect SQL database
    schemas, and analyze CSV, JSON, and MongoDB datasources to discover
    structure, types, and native metadata.
    No network access, no file writes.

    Args:
        config: SDC Agents configuration.
        model: LLM model identifier. Defaults to config.model.default.

    Returns:
        Configured LlmAgent with IntrospectToolset.
    """
    resolved_model = model or config.model.default or _DEFAULT_MODEL
    return LlmAgent(
        name="introspect_agent",
        model=resolved_model,
        description=(
            "Extracts structure from customer datasources "
            "(SQL databases, CSV, JSON, MongoDB). "
            "Read-only access, no network calls."
        ),
        instruction=(
            "You are the Introspect Agent. Your job is to help users understand "
            "the structure of their datasources.\n\n"
            "You can:\n"
            "- Execute SELECT queries against configured SQL datasources\n"
            "- Introspect SQL database schemas (columns, types, keys, constraints)\n"
            "- Introspect CSV files to discover columns and infer types\n"
            "- Introspect JSON files with optional JSONPath extraction\n"
            "- Introspect MongoDB collections with native validator metadata\n"
            "- Detect schema drift by comparing current structure against cached "
            "previous introspection (works with all datasource types)\n\n"
            "All introspection tools return a standardized 13-field column format "
            "including description, constraints, relationships, and metadata.\n\n"
            "You CANNOT:\n"
            "- Execute write operations (INSERT, UPDATE, DELETE, DROP, etc.)\n"
            "- Access the SDCStudio API\n"
            "- Access datasources not listed in the configuration\n"
            "- Make network calls\n\n"
            "Always use datasource names from the configuration, never raw "
            "connection strings or file paths. When introspecting, suggest "
            "the most specific type that fits the data."
        ),
        tools=[IntrospectToolset(config=config)],
    )

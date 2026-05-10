"""Notion database introspection toolset — ToolsetHub reference implementation.

Introspects Notion databases via the Notion API to discover property
structure, types, relations, and sample data. Produces the standard
13-field column format for downstream pipeline compatibility.

Requires: pip install sdc-agents-smb[notion]
"""

from __future__ import annotations

import json
import time
from typing import Optional

from google.adk.tools import FunctionTool
from google.adk.tools.base_toolset import BaseToolset

from sdc_agents.common.audit import AuditLogger
from sdc_agents.common.cache import CacheManager
from sdc_agents.common.config import SDCAgentsConfig

try:
    from notion_client import Client as NotionClient
except ImportError:
    NotionClient = None  # type: ignore[assignment, misc]

# Notion property type to SDC inferred type mapping
_NOTION_TYPE_MAP = {
    "title": "string",
    "rich_text": "string",
    "number": "decimal",
    "select": "string",
    "status": "string",
    "multi_select": "array",
    "date": "datetime",
    "people": "array",
    "files": "array",
    "checkbox": "boolean",
    "url": "URL",
    "email": "email",
    "phone_number": "string",
    "formula": "string",
    "relation": "string",
    "rollup": "string",
    "created_time": "datetime",
    "created_by": "string",
    "last_edited_time": "datetime",
    "last_edited_by": "string",
    "unique_id": "integer",
}


def _make_column(
    name: str,
    data_type: str,
    sample_values: list | None = None,
    description: str = "",
    enumeration: dict | None = None,
    units: str = "",
    nullable: bool | None = None,
    constraints: dict | None = None,
    range_values: str = "",
    relationships: str = "",
    business_rules: str = "",
    examples: str = "",
    metadata: dict | None = None,
) -> dict:
    """Build a standardized column dict (same as IntrospectToolset._make_column)."""
    return {
        "name": name,
        "data_type": data_type,
        "sample_values": sample_values or [],
        "description": description,
        "enumeration": enumeration,
        "units": units,
        "nullable": nullable,
        "constraints": constraints or {},
        "range_values": range_values,
        "relationships": relationships,
        "business_rules": business_rules,
        "examples": examples,
        "metadata": metadata or {},
    }


class NotionIntrospectToolset(BaseToolset):
    """ToolsetHub toolset for Notion database introspection."""

    def __init__(self, config: SDCAgentsConfig, **kwargs):
        super().__init__(**kwargs)
        self._config = config
        self._cache = CacheManager(config.cache.root)
        self._cache.ensure_dirs()
        self._audit = AuditLogger(config.audit.path, config.audit.log_level)

    async def get_tools(self) -> list[FunctionTool]:
        return [FunctionTool(self.introspect_notion)]

    async def introspect_notion(self, datasource_name: str, max_rows: int = 100) -> dict:
        """Introspect a Notion database to discover property structure and types.

        Queries the Notion API for database schema (properties) and sample
        data. Maps Notion property types to SDC standardized types.

        Args:
            datasource_name: Name of a configured Notion datasource (from config).
            max_rows: Maximum pages to sample for value extraction (default 100).

        Returns:
            Dict with datasource name, type, columns (13-field format),
            and row_count.
        """
        if NotionClient is None:
            raise ImportError(
                "notion-client is required for Notion introspection. "
                "Install with: pip install sdc-agents-smb[notion]"
            )

        start = time.monotonic()

        if datasource_name not in self._config.datasources:
            raise KeyError(
                f"Unknown datasource '{datasource_name}'. "
                f"Available: {list(self._config.datasources.keys())}"
            )

        ds = self._config.datasources[datasource_name]
        if ds.type != "notion":
            raise ValueError(f"Datasource '{datasource_name}' is type '{ds.type}', not 'notion'")

        if not ds.notion_token or not ds.notion_database_id:
            raise ValueError(
                f"Notion datasource '{datasource_name}' missing notion_token or notion_database_id"
            )

        client = NotionClient(auth=ds.notion_token)

        # Get database schema (properties)
        db_info = client.databases.retrieve(database_id=ds.notion_database_id)
        properties = db_info.get("properties", {})

        # Query sample pages for value extraction
        query_result = client.databases.query(
            database_id=ds.notion_database_id,
            page_size=min(max_rows, 100),
        )
        pages = query_result.get("results", [])

        columns = []
        for prop_name, prop_config in properties.items():
            prop_type = prop_config.get("type", "")
            inferred_type = _NOTION_TYPE_MAP.get(prop_type, "string")

            # Extract enumeration for select/status types
            enumeration = None
            if prop_type in ("select", "status"):
                options = prop_config.get(prop_type, {}).get("options", [])
                if options:
                    enumeration = {opt["name"]: opt.get("color", "") for opt in options}

            if prop_type == "multi_select":
                options = prop_config.get("multi_select", {}).get("options", [])
                if options:
                    enumeration = {opt["name"]: opt.get("color", "") for opt in options}

            # Extract relationship target
            relationships = ""
            if prop_type == "relation":
                rel_config = prop_config.get("relation", {})
                target_db = rel_config.get("database_id", "")
                if target_db:
                    relationships = f"relation to database {target_db}"

            # Number format
            if prop_type == "number":
                num_format = prop_config.get("number", {}).get("format", "")
                if num_format in ("number", "number_with_commas"):
                    inferred_type = "decimal"
                elif num_format == "percent":
                    inferred_type = "decimal"

            # Extract sample values from pages
            sample_values = []
            for page in pages[:5]:
                page_props = page.get("properties", {})
                prop_data = page_props.get(prop_name, {})
                val = self._extract_property_value(prop_data, prop_type)
                if val is not None:
                    sample_values.append(val)

            columns.append(
                _make_column(
                    name=prop_name,
                    data_type=inferred_type,
                    sample_values=sample_values,
                    description=f"Notion {prop_type} property",
                    enumeration=enumeration,
                    nullable=True,
                    relationships=relationships,
                    metadata={
                        "source_type": "notion",
                        "notion_property_type": prop_type,
                        "notion_property_id": prop_config.get("id", ""),
                    },
                )
            )

        result = {
            "datasource": datasource_name,
            "type": "notion",
            "columns": columns,
            "row_count": len(pages),
            "database_title": self._extract_title(db_info.get("title", [])),
        }

        # Write to cache
        cache_path = self._cache.introspection_path(datasource_name)
        cache_path.write_text(json.dumps(result, indent=2, default=str))

        self._audit.log(
            agent="introspect",
            tool="introspect_notion",
            inputs={"datasource_name": datasource_name, "max_rows": max_rows},
            outputs=result,
            start_time=start,
        )
        return result

    @staticmethod
    def _extract_property_value(prop_data: dict, prop_type: str) -> Optional[str]:
        """Extract a displayable value from a Notion property object."""
        if not prop_data:
            return None

        if prop_type == "title":
            texts = prop_data.get("title", [])
            return "".join(t.get("plain_text", "") for t in texts) or None
        if prop_type == "rich_text":
            texts = prop_data.get("rich_text", [])
            return "".join(t.get("plain_text", "") for t in texts) or None
        if prop_type == "number":
            return str(prop_data.get("number")) if prop_data.get("number") is not None else None
        if prop_type == "select":
            sel = prop_data.get("select")
            return sel.get("name") if sel else None
        if prop_type == "status":
            st = prop_data.get("status")
            return st.get("name") if st else None
        if prop_type == "multi_select":
            options = prop_data.get("multi_select", [])
            return ", ".join(o.get("name", "") for o in options) if options else None
        if prop_type == "date":
            dt = prop_data.get("date")
            return dt.get("start") if dt else None
        if prop_type == "checkbox":
            return str(prop_data.get("checkbox", False))
        if prop_type == "url":
            return prop_data.get("url")
        if prop_type == "email":
            return prop_data.get("email")
        if prop_type == "phone_number":
            return prop_data.get("phone_number")
        if prop_type in ("created_time", "last_edited_time"):
            return prop_data.get(prop_type)
        if prop_type == "formula":
            formula = prop_data.get("formula", {})
            return str(formula.get(formula.get("type", ""), ""))
        return None

    @staticmethod
    def _extract_title(title_array: list) -> str:
        """Extract plain text from a Notion title array."""
        return "".join(t.get("plain_text", "") for t in title_array)

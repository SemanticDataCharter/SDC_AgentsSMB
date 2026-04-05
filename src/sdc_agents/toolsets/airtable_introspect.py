"""Airtable base introspection toolset — ToolsetHub reference implementation.

Introspects Airtable bases via the Airtable API to discover field
structure, types, linked records, and sample data. Produces the
standard 13-field column format.

Requires: pip install sdc-agents-smb[airtable]
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
    from pyairtable import Api as AirtableApi
except ImportError:
    AirtableApi = None  # type: ignore[assignment, misc]

# Airtable field type to SDC inferred type mapping
_AIRTABLE_TYPE_MAP = {
    "singleLineText": "string",
    "multilineText": "string",
    "richText": "string",
    "email": "email",
    "url": "URL",
    "phoneNumber": "string",
    "number": "decimal",
    "currency": "decimal",
    "percent": "decimal",
    "count": "integer",
    "autoNumber": "integer",
    "rating": "integer",
    "duration": "decimal",
    "checkbox": "boolean",
    "date": "date",
    "dateTime": "datetime",
    "createdTime": "datetime",
    "lastModifiedTime": "datetime",
    "singleSelect": "string",
    "multipleSelects": "array",
    "singleCollaborator": "string",
    "multipleCollaborators": "array",
    "multipleRecordLinks": "array",
    "multipleAttachments": "array",
    "formula": "string",
    "lookup": "string",
    "rollup": "string",
    "barcode": "string",
    "button": "string",
    "externalSyncSource": "string",
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


class AirtableIntrospectToolset(BaseToolset):
    """ToolsetHub toolset for Airtable base introspection."""

    def __init__(self, config: SDCAgentsConfig, **kwargs):
        super().__init__(**kwargs)
        self._config = config
        self._cache = CacheManager(config.cache.root)
        self._cache.ensure_dirs()
        self._audit = AuditLogger(config.audit.path, config.audit.log_level)

    async def get_tools(self) -> list[FunctionTool]:
        return [FunctionTool(self.introspect_airtable)]

    async def introspect_airtable(
        self, datasource_name: str, max_rows: int = 100
    ) -> dict:
        """Introspect an Airtable table to discover field structure and types.

        Queries the Airtable API for table schema (fields) and sample
        records. Maps Airtable field types to SDC standardized types.

        Args:
            datasource_name: Name of a configured Airtable datasource (from config).
            max_rows: Maximum records to sample (default 100).

        Returns:
            Dict with datasource name, type, columns (13-field format),
            and row_count.
        """
        if AirtableApi is None:
            raise ImportError(
                "pyairtable is required for Airtable introspection. "
                "Install with: pip install sdc-agents-smb[airtable]"
            )

        start = time.monotonic()

        if datasource_name not in self._config.datasources:
            raise KeyError(
                f"Unknown datasource '{datasource_name}'. "
                f"Available: {list(self._config.datasources.keys())}"
            )

        ds = self._config.datasources[datasource_name]
        if ds.type != "airtable":
            raise ValueError(
                f"Datasource '{datasource_name}' is type '{ds.type}', not 'airtable'"
            )

        if not ds.airtable_token or not ds.airtable_base_id or not ds.airtable_table:
            raise ValueError(
                f"Airtable datasource '{datasource_name}' missing airtable_token, "
                "airtable_base_id, or airtable_table"
            )

        api = AirtableApi(ds.airtable_token)
        table = api.table(ds.airtable_base_id, ds.airtable_table)

        # Get table schema via metadata API
        base = api.base(ds.airtable_base_id)
        table_schema = None
        try:
            schema = base.schema()
            for tbl in schema.tables:
                if tbl.name == ds.airtable_table or tbl.id == ds.airtable_table:
                    table_schema = tbl
                    break
        except Exception:
            pass  # Schema API may not be available on all plans

        # Get sample records
        records = table.all(max_records=max_rows)

        # Build columns from schema if available, otherwise from record keys
        columns = []

        if table_schema and hasattr(table_schema, "fields"):
            for field in table_schema.fields:
                field_type = field.type if hasattr(field, "type") else "singleLineText"
                field_name = field.name if hasattr(field, "name") else str(field)
                inferred_type = _AIRTABLE_TYPE_MAP.get(field_type, "string")

                # Extract enumeration for select fields
                enumeration = None
                if field_type == "singleSelect" and hasattr(field, "options"):
                    opts = field.options
                    if hasattr(opts, "choices") and opts.choices:
                        enumeration = {c.name: c.color if hasattr(c, "color") else "" for c in opts.choices}

                # Extract relationships for linked records
                relationships = ""
                if field_type == "multipleRecordLinks" and hasattr(field, "options"):
                    opts = field.options
                    if hasattr(opts, "linked_table_id"):
                        relationships = f"linked to table {opts.linked_table_id}"

                # Sample values from records
                sample_values = []
                for rec in records[:5]:
                    val = rec.get("fields", {}).get(field_name)
                    if val is not None:
                        sample_values.append(str(val) if not isinstance(val, str) else val)

                columns.append(
                    _make_column(
                        name=field_name,
                        data_type=inferred_type,
                        sample_values=sample_values,
                        description=field.description if hasattr(field, "description") and field.description else f"Airtable {field_type} field",
                        enumeration=enumeration,
                        nullable=True,
                        relationships=relationships,
                        metadata={
                            "source_type": "airtable",
                            "airtable_field_type": field_type,
                            "airtable_field_id": field.id if hasattr(field, "id") else "",
                        },
                    )
                )
        else:
            # Fallback: infer from record data
            if records:
                all_keys: dict[str, list] = {}
                for rec in records:
                    for key, val in rec.get("fields", {}).items():
                        all_keys.setdefault(key, []).append(val)

                for key, values in all_keys.items():
                    str_values = [str(v) for v in values if v is not None]
                    from sdc_agents.toolsets.introspect import _infer_type
                    inferred = _infer_type(str_values) if str_values else "string"

                    columns.append(
                        _make_column(
                            name=key,
                            data_type=inferred,
                            sample_values=str_values[:5],
                            metadata={"source_type": "airtable", "airtable_field_type": "unknown"},
                        )
                    )

        result = {
            "datasource": datasource_name,
            "type": "airtable",
            "columns": columns,
            "row_count": len(records),
            "table_name": ds.airtable_table,
        }

        # Write to cache
        cache_path = self._cache.introspection_path(datasource_name)
        cache_path.write_text(json.dumps(result, indent=2, default=str))

        self._audit.log(
            agent="introspect",
            tool="introspect_airtable",
            inputs={"datasource_name": datasource_name, "max_rows": max_rows},
            outputs=result,
            start_time=start,
        )
        return result

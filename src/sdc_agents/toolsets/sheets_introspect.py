"""Google Sheets introspection toolset — ToolsetHub reference implementation.

Introspects Google Sheets spreadsheets via the Sheets API to discover
column structure, infer types from cell values, and extract metadata.
Produces the standard 13-field column format.

Requires: pip install sdc-agents-smb[sheets]
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from google.adk.tools import FunctionTool
from google.adk.tools.base_toolset import BaseToolset

from sdc_agents.common.audit import AuditLogger
from sdc_agents.common.cache import CacheManager
from sdc_agents.common.config import SDCAgentsConfig
from sdc_agents.toolsets.introspect import _infer_type

try:
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build as build_service
except ImportError:
    Credentials = None  # type: ignore[assignment, misc]
    build_service = None  # type: ignore[assignment]


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


class SheetsIntrospectToolset(BaseToolset):
    """ToolsetHub toolset for Google Sheets introspection."""

    def __init__(self, config: SDCAgentsConfig, **kwargs):
        super().__init__(**kwargs)
        self._config = config
        self._cache = CacheManager(config.cache.root)
        self._cache.ensure_dirs()
        self._audit = AuditLogger(config.audit.path, config.audit.log_level)

    async def get_tools(self) -> list[FunctionTool]:
        return [FunctionTool(self.introspect_sheets)]

    async def introspect_sheets(self, datasource_name: str, max_rows: int = 100) -> dict:
        """Introspect a Google Sheets spreadsheet to discover column structure.

        Reads headers and sample data from the specified sheet, then infers
        column types from cell values using the same type inference as CSV
        introspection.

        Args:
            datasource_name: Name of a configured Sheets datasource (from config).
            max_rows: Maximum rows to read for type inference (default 100).

        Returns:
            Dict with datasource name, type, columns (13-field format),
            and row_count.
        """
        if Credentials is None or build_service is None:
            raise ImportError(
                "google-api-python-client and google-auth are required for Sheets "
                "introspection. Install with: pip install sdc-agents-smb[sheets]"
            )

        start = time.monotonic()

        if datasource_name not in self._config.datasources:
            raise KeyError(
                f"Unknown datasource '{datasource_name}'. "
                f"Available: {list(self._config.datasources.keys())}"
            )

        ds = self._config.datasources[datasource_name]
        if ds.type != "sheets":
            raise ValueError(f"Datasource '{datasource_name}' is type '{ds.type}', not 'sheets'")

        if not ds.sheets_credentials or not ds.spreadsheet_id:
            raise ValueError(
                f"Sheets datasource '{datasource_name}' missing sheets_credentials "
                "or spreadsheet_id"
            )

        # Authenticate via service account
        creds_path = Path(ds.sheets_credentials)
        if not creds_path.is_file():
            raise FileNotFoundError(f"Sheets credentials file not found: {ds.sheets_credentials}")

        creds = Credentials.from_service_account_file(
            str(creds_path),
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
        )
        service = build_service("sheets", "v4", credentials=creds)

        # Determine range
        sheet_name = ds.sheet_name or "Sheet1"
        range_str = f"'{sheet_name}'!A1:{max_rows + 1}"

        # Fetch data
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=ds.spreadsheet_id, range=range_str)
            .execute()
        )
        rows = result.get("values", [])

        if not rows:
            return {
                "datasource": datasource_name,
                "type": "sheets",
                "columns": [],
                "row_count": 0,
                "sheet_name": sheet_name,
            }

        # First row is headers
        headers = rows[0]
        data_rows = rows[1:]

        # Collect values per column
        column_values: dict[str, list[str]] = {h: [] for h in headers}
        for row in data_rows:
            for i, header in enumerate(headers):
                val = row[i] if i < len(row) else ""
                column_values[header].append(str(val))

        columns = []
        for i, header in enumerate(headers):
            values = column_values[header]
            inferred = _infer_type(values)

            # Count nulls
            non_empty = [v for v in values if v.strip()]
            nullable = len(non_empty) < len(values)

            columns.append(
                _make_column(
                    name=header,
                    data_type=inferred,
                    sample_values=values[:5],
                    nullable=nullable,
                    metadata={
                        "source_type": "sheets",
                        "sheet_name": sheet_name,
                        "column_index": i,
                    },
                )
            )

        introspection_result = {
            "datasource": datasource_name,
            "type": "sheets",
            "columns": columns,
            "row_count": len(data_rows),
            "sheet_name": sheet_name,
        }

        # Write to cache
        cache_path = self._cache.introspection_path(datasource_name)
        cache_path.write_text(json.dumps(introspection_result, indent=2, default=str))

        self._audit.log(
            agent="introspect",
            tool="introspect_sheets",
            inputs={"datasource_name": datasource_name, "max_rows": max_rows},
            outputs=introspection_result,
            start_time=start,
        )
        return introspection_result

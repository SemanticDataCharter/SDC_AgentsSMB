"""Introspect Toolset — read-only datasource structure extraction.

Provides SQL (SELECT-only), CSV, JSON, and MongoDB introspection tools.
No network access, no file system writes.
"""

from __future__ import annotations

import csv
import io
import json
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from google.adk.tools import FunctionTool
from google.adk.tools.base_toolset import BaseToolset

from sdc_agents.common.audit import AuditLogger
from sdc_agents.common.cache import CacheManager
from sdc_agents.common.config import SDCAgentsConfig

# Regex to reject write operations — anchored to start of statement
_WRITE_PATTERN = re.compile(
    r"^\s*(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|REPLACE|MERGE)\b",
    re.IGNORECASE,
)

# Type inference patterns ordered by specificity
_BOOL_VALUES = {"true", "false", "yes", "no", "1", "0", "t", "f", "y", "n"}
_INTEGER_PATTERN = re.compile(r"^-?\d+$")
_DECIMAL_PATTERN = re.compile(r"^-?\d+\.\d+$")
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATETIME_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}")
_TIME_PATTERN = re.compile(r"^\d{2}:\d{2}(:\d{2})?$")
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_URL_PATTERN = re.compile(r"^https?://\S+$")
_UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)

# BSON type to inferred type mapping
_BSON_TYPE_MAP = {
    "string": "string",
    "int": "integer",
    "int32": "integer",
    "int64": "integer",
    "long": "integer",
    "double": "decimal",
    "decimal": "decimal",
    "decimal128": "decimal",
    "bool": "boolean",
    "date": "datetime",
    "timestamp": "datetime",
    "objectId": "objectId",
    "array": "array",
    "object": "object",
    "null": "null",
    "binData": "binary",
    "regex": "string",
}

# SQL type name to inferred type mapping (case-insensitive lookup via upper())
_SQL_TYPE_MAP = {
    "INTEGER": "integer",
    "INT": "integer",
    "SMALLINT": "integer",
    "BIGINT": "integer",
    "TINYINT": "integer",
    "MEDIUMINT": "integer",
    "SERIAL": "integer",
    "REAL": "decimal",
    "FLOAT": "decimal",
    "DOUBLE": "decimal",
    "DOUBLE PRECISION": "decimal",
    "NUMERIC": "decimal",
    "DECIMAL": "decimal",
    "MONEY": "decimal",
    "VARCHAR": "string",
    "CHAR": "string",
    "CHARACTER VARYING": "string",
    "TEXT": "string",
    "CLOB": "string",
    "NVARCHAR": "string",
    "NCHAR": "string",
    "NTEXT": "string",
    "BOOLEAN": "boolean",
    "BOOL": "boolean",
    "DATE": "date",
    "DATETIME": "datetime",
    "DATETIME2": "datetime",
    "TIMESTAMP": "datetime",
    "TIMESTAMP WITHOUT TIME ZONE": "datetime",
    "TIMESTAMP WITH TIME ZONE": "datetime",
    "TIME": "time",
    "TIME WITHOUT TIME ZONE": "time",
    "TIME WITH TIME ZONE": "time",
    "BLOB": "binary",
    "BYTEA": "binary",
    "BINARY": "binary",
    "VARBINARY": "binary",
    "IMAGE": "binary",
    "JSON": "object",
    "JSONB": "object",
    "XML": "string",
    "UUID": "UUID",
    "UNIQUEIDENTIFIER": "UUID",
    "ARRAY": "array",
    "INET": "string",
    "CIDR": "string",
    "MACADDR": "string",
}


def _sql_type_to_inferred(sql_type_str: str) -> str:
    """Map a raw SQL type string to an inferred type.

    Handles parameterized types like VARCHAR(255) by stripping the parenthetical.
    """
    # Strip parenthetical (e.g., "VARCHAR(255)" -> "VARCHAR")
    base = sql_type_str.split("(")[0].strip().upper()
    return _SQL_TYPE_MAP.get(base, "string")


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
    """Build a standardized column dict for introspection output."""
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


def _infer_type(values: list[str]) -> str:
    """Infer the most specific type from a list of sample string values.

    Order: boolean > integer > decimal > date > datetime > time > email > URL > UUID > string
    """
    non_empty = [v.strip() for v in values if v.strip()]
    if not non_empty:
        return "string"

    # Check each type — all non-empty values must match
    if all(v.lower() in _BOOL_VALUES for v in non_empty):
        return "boolean"
    if all(_INTEGER_PATTERN.match(v) for v in non_empty):
        return "integer"
    if all(_DECIMAL_PATTERN.match(v) for v in non_empty):
        return "decimal"
    if all(_DATE_PATTERN.match(v) for v in non_empty):
        return "date"
    if all(_DATETIME_PATTERN.match(v) for v in non_empty):
        return "datetime"
    if all(_TIME_PATTERN.match(v) for v in non_empty):
        return "time"
    if all(_EMAIL_PATTERN.match(v) for v in non_empty):
        return "email"
    if all(_URL_PATTERN.match(v) for v in non_empty):
        return "URL"
    if all(_UUID_PATTERN.match(v) for v in non_empty):
        return "UUID"
    return "string"


def _infer_json_type(value: object) -> str:
    """Infer a type string from a Python/JSON value."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "decimal"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    # For strings, use _infer_type for more specific detection
    s = str(value)
    return _infer_type([s])


def _bson_type_name(value: object) -> str:
    """Return a BSON-style type name for a Python value."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "double"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    type_name = type(value).__name__
    # Handle common BSON types from motor/pymongo
    if type_name == "ObjectId":
        return "objectId"
    if type_name in ("datetime", "Timestamp"):
        return "date"
    if type_name == "Decimal128":
        return "decimal128"
    return "string"


class IntrospectToolset(BaseToolset):
    """Scoped toolset for datasource structure extraction.

    Read-only access to configured datasources. SQL queries are
    restricted to SELECT statements only.
    """

    def __init__(self, config: SDCAgentsConfig, **kwargs):
        super().__init__(**kwargs)
        self._config = config
        self._cache = CacheManager(config.cache.root)
        self._cache.ensure_dirs()
        self._audit = AuditLogger(config.audit.path, config.audit.log_level)

    async def get_tools(self, readonly_context=None) -> list:
        """Return the introspection tools as FunctionTool instances."""
        tools = [
            FunctionTool(self.introspect_sql),
            FunctionTool(self.introspect_sql_schema),
            FunctionTool(self.introspect_csv),
            FunctionTool(self.introspect_json),
            FunctionTool(self.introspect_mongodb),
            FunctionTool(self.detect_schema_drift),
        ]
        if readonly_context and self.tool_filter:
            return [t for t in tools if self._is_tool_selected(t, readonly_context)]
        return tools

    def _get_datasource(self, name: str):
        """Look up a datasource by name from config. Raises KeyError if unknown."""
        if name not in self._config.datasources:
            raise KeyError(
                f"Unknown datasource '{name}'. "
                f"Available: {list(self._config.datasources.keys())}"
            )
        return self._config.datasources[name]

    async def introspect_sql(self, datasource_name: str, query: str) -> list[dict]:
        """Execute a read-only SQL query against a configured datasource.

        Only SELECT statements are allowed. INSERT, UPDATE, DELETE, DROP,
        ALTER, CREATE, TRUNCATE, REPLACE, and MERGE are rejected.

        Args:
            datasource_name: Name of a configured SQL datasource (from config).
            query: SQL SELECT query to execute.

        Returns:
            List of row dictionaries with column names as keys.
        """
        start = time.monotonic()
        ds = self._get_datasource(datasource_name)

        if ds.type != "sql":
            raise ValueError(f"Datasource '{datasource_name}' is type '{ds.type}', not 'sql'")

        # Enforce read-only
        if _WRITE_PATTERN.match(query):
            raise PermissionError(
                f"Write operations are not allowed. Only SELECT queries are permitted. "
                f"Rejected query: {query[:100]}"
            )

        import sqlalchemy
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(ds.connection_string)
        try:
            async with engine.connect() as conn:
                result = await conn.execute(sqlalchemy.text(query))
                columns = list(result.keys())
                rows = [dict(zip(columns, row)) for row in result.fetchall()]
        finally:
            await engine.dispose()

        self._audit.log(
            agent="introspect",
            tool="introspect_sql",
            inputs={"datasource_name": datasource_name, "query": query},
            outputs=rows,
            start_time=start,
        )
        return rows

    async def introspect_csv(self, datasource_name: str, max_rows: int = 100) -> dict:
        """Introspect a CSV datasource to discover column structure and types.

        Reads the CSV file, infers types from sample values, and returns
        column metadata.

        Args:
            datasource_name: Name of a configured CSV datasource (from config).
            max_rows: Maximum rows to read for type inference (default 100).

        Returns:
            Dict with datasource name, type, columns (name, inferred_type,
            sample_values), and row_count.
        """
        start = time.monotonic()
        ds = self._get_datasource(datasource_name)

        if ds.type != "csv":
            raise ValueError(f"Datasource '{datasource_name}' is type '{ds.type}', not 'csv'")

        csv_path = Path(ds.path)
        if not csv_path.is_file():
            raise FileNotFoundError(f"CSV file not found: {ds.path}")

        content = csv_path.read_text()
        reader = csv.DictReader(io.StringIO(content))
        fieldnames = reader.fieldnames or []

        # Collect values per column
        column_values: dict[str, list[str]] = {name: [] for name in fieldnames}
        row_count = 0
        for row in reader:
            if row_count >= max_rows:
                break
            for name in fieldnames:
                column_values[name].append(row.get(name, ""))
            row_count += 1

        columns = []
        for name in fieldnames:
            values = column_values[name]
            columns.append(
                _make_column(
                    name=name,
                    data_type=_infer_type(values),
                    sample_values=values[:5],
                )
            )

        # Merge sidecar metadata if configured
        metadata_path = ds.metadata_path
        if metadata_path:
            meta_file = Path(metadata_path)
            if meta_file.is_file():
                sidecar = json.loads(meta_file.read_text())
                col_meta = sidecar.get("columns", {})
                for col in columns:
                    meta = col_meta.get(col["name"], {})
                    desc = meta.get("description") or meta.get("label", "")
                    if desc:
                        col["description"] = desc
                    if meta.get("value_labels"):
                        col["enumeration"] = meta["value_labels"]
                    if meta.get("units"):
                        col["units"] = meta["units"]
                    if meta.get("range_values"):
                        col["range_values"] = meta["range_values"]
                    if meta.get("relationships"):
                        col["relationships"] = meta["relationships"]
                    if meta.get("business_rules"):
                        col["business_rules"] = meta["business_rules"]
                    if meta.get("examples"):
                        col["examples"] = meta["examples"]
                    if meta.get("metadata"):
                        col["metadata"].update(meta["metadata"])

        result = {
            "datasource": datasource_name,
            "type": "csv",
            "columns": columns,
            "row_count": row_count,
        }

        # Write to introspection cache for downstream toolsets
        cache_path = self._cache.introspection_path(datasource_name)
        cache_path.write_text(json.dumps(result, indent=2, default=str))

        self._audit.log(
            agent="introspect",
            tool="introspect_csv",
            inputs={"datasource_name": datasource_name, "max_rows": max_rows},
            outputs=result,
            start_time=start,
        )
        return result

    async def introspect_json(
        self,
        datasource_name: str,
        jsonpath: Optional[str] = None,
    ) -> dict:
        """Introspect a JSON datasource to discover structure and types.

        Reads a JSON file, optionally extracts records via JSONPath, and
        infers types from values.

        Args:
            datasource_name: Name of a configured JSON datasource (from config).
            jsonpath: Optional JSONPath expression to extract records. Overrides
                the config-level jsonpath if provided.

        Returns:
            Dict with datasource name, type, columns (name, inferred_type,
            sample_values), and row_count.
        """
        start = time.monotonic()
        ds = self._get_datasource(datasource_name)

        if ds.type != "json":
            raise ValueError(f"Datasource '{datasource_name}' is type '{ds.type}', not 'json'")

        json_path = Path(ds.path)
        if not json_path.is_file():
            raise FileNotFoundError(f"JSON file not found: {ds.path}")

        raw = json.loads(json_path.read_text())

        # Apply JSONPath extraction if specified
        jp_expr = jsonpath or ds.jsonpath
        if jp_expr:
            from jsonpath_ng import parse as jp_parse

            expression = jp_parse(jp_expr)
            matches = expression.find(raw)
            records = [m.value for m in matches]
        else:
            # If raw is a list, use directly; otherwise wrap in list
            records = raw if isinstance(raw, list) else [raw]

        # Analyze records — expect list of dicts (or mixed)
        column_values: dict[str, list] = {}
        row_count = 0
        for record in records:
            if not isinstance(record, dict):
                continue
            row_count += 1
            for key, value in record.items():
                column_values.setdefault(key, []).append(value)

        columns = []
        for name, values in column_values.items():
            # Infer type from string representations for string inference,
            # or use direct type inference for JSON native types
            str_values = [str(v) for v in values if v is not None]
            if str_values:
                inferred = _infer_type(str_values)
            else:
                inferred = "string"

            # Override with more specific JSON-native types
            non_null = [v for v in values if v is not None]
            if non_null:
                first = non_null[0]
                if isinstance(first, dict):
                    inferred = "object"
                elif isinstance(first, list):
                    inferred = "array"

            columns.append(
                _make_column(
                    name=name,
                    data_type=inferred,
                    sample_values=values[:5],
                )
            )

        # Merge sidecar metadata if configured
        metadata_path = ds.metadata_path
        if metadata_path:
            meta_file = Path(metadata_path)
            if meta_file.is_file():
                sidecar = json.loads(meta_file.read_text())
                col_meta = sidecar.get("columns", {})
                for col in columns:
                    meta = col_meta.get(col["name"], {})
                    desc = meta.get("description") or meta.get("label", "")
                    if desc:
                        col["description"] = desc
                    if meta.get("value_labels"):
                        col["enumeration"] = meta["value_labels"]
                    if meta.get("units"):
                        col["units"] = meta["units"]
                    if meta.get("range_values"):
                        col["range_values"] = meta["range_values"]
                    if meta.get("relationships"):
                        col["relationships"] = meta["relationships"]
                    if meta.get("business_rules"):
                        col["business_rules"] = meta["business_rules"]
                    if meta.get("examples"):
                        col["examples"] = meta["examples"]
                    if meta.get("metadata"):
                        col["metadata"].update(meta["metadata"])

        result = {
            "datasource": datasource_name,
            "type": "json",
            "columns": columns,
            "row_count": row_count,
        }

        # Write to introspection cache for downstream toolsets
        cache_path = self._cache.introspection_path(datasource_name)
        cache_path.write_text(json.dumps(result, indent=2, default=str))

        self._audit.log(
            agent="introspect",
            tool="introspect_json",
            inputs={"datasource_name": datasource_name, "jsonpath": jp_expr},
            outputs=result,
            start_time=start,
        )
        return result

    async def introspect_mongodb(
        self,
        datasource_name: str,
        collection: Optional[str] = None,
        sample_size: int = 100,
    ) -> dict:
        """Introspect a MongoDB collection to discover document structure.

        Samples documents from a MongoDB collection and analyzes field types.
        Read-only: only find() calls, no inserts/updates/deletes.

        Args:
            datasource_name: Name of a configured MongoDB datasource (from config).
            collection: Collection name. Overrides config-level collection if provided.
            sample_size: Number of documents to sample (default 100).

        Returns:
            Dict with datasource, collection, fields (name, bson_type, nullable,
            sample_values), and document_count.
        """
        start = time.monotonic()
        ds = self._get_datasource(datasource_name)

        if ds.type != "mongodb":
            raise ValueError(f"Datasource '{datasource_name}' is type '{ds.type}', not 'mongodb'")

        coll_name = collection or ds.collection
        if not coll_name:
            raise ValueError(
                f"No collection specified for datasource '{datasource_name}'. "
                "Provide via tool parameter or datasource config."
            )

        db_name = ds.database
        if not db_name:
            raise ValueError(
                f"No database specified for datasource '{datasource_name}'. "
                "Set 'database' in datasource config."
            )

        from motor.motor_asyncio import AsyncIOMotorClient

        client = AsyncIOMotorClient(ds.connection_string)
        try:
            db = client[db_name]
            coll = db[coll_name]

            # Try to fetch JSON Schema validator for native metadata
            validator_schema: dict | None = None
            try:
                coll_info = await db.command("listCollections", filter={"name": coll_name})
                first_batch = coll_info.get("cursor", {}).get("firstBatch", [])
                if first_batch:
                    options = first_batch[0].get("options", {})
                    validator = options.get("validator", {})
                    validator_schema = validator.get("$jsonSchema")
            except Exception:
                pass  # No validator — proceed with sampling only

            # Sample documents (read-only)
            cursor = coll.find().limit(sample_size)
            docs = await cursor.to_list(length=sample_size)
            doc_count = await coll.count_documents({})

            # Analyze fields across all sampled documents
            field_info: dict[str, dict] = {}
            for doc in docs:
                for key, value in doc.items():
                    if key not in field_info:
                        field_info[key] = {
                            "types": set(),
                            "nullable": False,
                            "sample_values": [],
                        }
                    info = field_info[key]
                    btype = _bson_type_name(value)
                    info["types"].add(btype)
                    if value is None:
                        info["nullable"] = True
                    if len(info["sample_values"]) < 5:
                        # Convert ObjectId etc. to string for serialization
                        sample_val = str(value) if btype == "objectId" else value
                        info["sample_values"].append(sample_val)

                # Check for fields present in schema but missing in this doc
                for known_key in list(field_info.keys()):
                    if known_key not in doc:
                        field_info[known_key]["nullable"] = True

            # Extract validator metadata per field
            validator_props = {}
            validator_required: set = set()
            if validator_schema:
                validator_props = validator_schema.get("properties", {})
                validator_required = set(validator_schema.get("required", []))

            fields = []
            for name, info in field_info.items():
                # Pick the most common non-null type
                types = info["types"] - {"null"}
                bson_type = next(iter(types)) if types else "null"

                # Build constraints and metadata from validator
                description = ""
                enumeration = None
                constraints: dict = {}
                range_values = ""
                business_rules = ""
                field_metadata = {"bson_type": bson_type}

                vprop = validator_props.get(name, {})
                if vprop:
                    if vprop.get("description"):
                        description = vprop["description"]
                    if vprop.get("enum"):
                        enumeration = {str(v): str(v) for v in vprop["enum"]}
                    if "minimum" in vprop or "maximum" in vprop:
                        if "minimum" in vprop:
                            constraints["min"] = vprop["minimum"]
                        if "maximum" in vprop:
                            constraints["max"] = vprop["maximum"]
                        parts = []
                        if "minimum" in vprop:
                            parts.append(f"min={vprop['minimum']}")
                        if "maximum" in vprop:
                            parts.append(f"max={vprop['maximum']}")
                        range_values = ", ".join(parts)
                    if vprop.get("pattern"):
                        constraints["pattern"] = vprop["pattern"]
                        business_rules = f"pattern: {vprop['pattern']}"

                # Merge validator required with sampling-based nullable
                nullable = info["nullable"]
                if name in validator_required and not info["nullable"]:
                    nullable = False

                col = _make_column(
                    name=name,
                    data_type=_BSON_TYPE_MAP.get(bson_type, "string"),
                    sample_values=info["sample_values"],
                    description=description,
                    enumeration=enumeration,
                    nullable=nullable,
                    constraints=constraints,
                    range_values=range_values,
                    business_rules=business_rules,
                    metadata=field_metadata,
                )
                # Preserve backward-compat bson_type at top level
                col["bson_type"] = bson_type
                fields.append(col)
        finally:
            client.close()

        result = {
            "datasource": datasource_name,
            "collection": coll_name,
            "columns": fields,
            "row_count": doc_count,
        }

        # Write to introspection cache for downstream toolsets
        cache_path = self._cache.introspection_path(datasource_name)
        cache_path.write_text(json.dumps(result, indent=2, default=str))

        self._audit.log(
            agent="introspect",
            tool="introspect_mongodb",
            inputs={
                "datasource_name": datasource_name,
                "collection": coll_name,
                "sample_size": sample_size,
            },
            outputs=result,
            start_time=start,
        )
        return result

    async def introspect_sql_schema(
        self,
        datasource_name: str,
        table_name: str | None = None,
    ) -> dict:
        """Introspect a SQL database schema using catalog metadata.

        Uses SQLAlchemy's inspector to extract column types, nullability,
        primary keys, foreign keys, check constraints, and defaults.

        Args:
            datasource_name: Name of a configured SQL datasource (from config).
            table_name: Specific table to introspect. If omitted, introspects
                all tables in the database.

        Returns:
            Dict with datasource, type, and tables (each with columns in
            standardized 13-field format).
        """
        start = time.monotonic()
        ds = self._get_datasource(datasource_name)

        if ds.type != "sql":
            raise ValueError(f"Datasource '{datasource_name}' is type '{ds.type}', not 'sql'")

        from sqlalchemy import inspect as sa_inspect
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(ds.connection_string)
        try:

            def _inspect_sync(conn):
                inspector = sa_inspect(conn)
                table_names = [table_name] if table_name else inspector.get_table_names()
                tables = []
                for tbl in table_names:
                    # Get primary keys
                    try:
                        pk_info = inspector.get_pk_constraint(tbl)
                        pk_cols = set(pk_info.get("constrained_columns", []))
                    except Exception:
                        pk_cols = set()

                    # Get foreign keys
                    fk_map: dict[str, str] = {}
                    try:
                        for fk in inspector.get_foreign_keys(tbl):
                            ref_table = fk.get("referred_table", "")
                            ref_cols = fk.get("referred_columns", [])
                            for i, col_name in enumerate(fk.get("constrained_columns", [])):
                                ref_col = ref_cols[i] if i < len(ref_cols) else ""
                                fk_map[col_name] = f"{ref_table}.{ref_col}"
                    except Exception:
                        pass

                    # Get check constraints
                    check_map: dict[str, list[str]] = {}
                    try:
                        for ck in inspector.get_check_constraints(tbl):
                            sqltext = ck.get("sqltext", "")
                            # Try to associate with columns mentioned in the expression
                            for col_info in inspector.get_columns(tbl):
                                if col_info["name"] in sqltext:
                                    check_map.setdefault(col_info["name"], []).append(sqltext)
                    except Exception:
                        pass

                    # Get columns
                    columns = []
                    for col_info in inspector.get_columns(tbl):
                        col_name = col_info["name"]
                        raw_type = str(col_info["type"])
                        inferred = _sql_type_to_inferred(raw_type)

                        # Build constraints
                        constraints: dict = {}
                        if col_name in pk_cols:
                            constraints["primary_key"] = True
                        if col_info.get("autoincrement") is True:
                            constraints["autoincrement"] = True
                        if col_info.get("default") is not None:
                            default_val = col_info["default"]
                            if hasattr(default_val, "arg"):
                                constraints["default"] = str(default_val.arg)
                            else:
                                constraints["default"] = str(default_val)

                        # Relationships from FK
                        relationships = fk_map.get(col_name, "")

                        # Business rules from CHECK constraints
                        checks = check_map.get(col_name, [])
                        business_rules = "; ".join(checks) if checks else ""

                        # Description from column comment (PostgreSQL/MySQL)
                        description = col_info.get("comment", "") or ""

                        columns.append(
                            _make_column(
                                name=col_name,
                                data_type=inferred,
                                nullable=col_info.get("nullable"),
                                description=description,
                                constraints=constraints,
                                relationships=relationships,
                                business_rules=business_rules,
                                metadata={"sql_type": raw_type},
                            )
                        )
                    tables.append(
                        {
                            "table": tbl,
                            "columns": columns,
                        }
                    )
                return tables

            async with engine.connect() as conn:
                tables = await conn.run_sync(_inspect_sync)
        finally:
            await engine.dispose()

        # Flatten all table columns into top-level columns list
        all_columns = []
        for tbl_info in tables:
            for col in tbl_info["columns"]:
                col["metadata"]["source_table"] = tbl_info["table"]
                all_columns.append(col)

        result = {
            "datasource": datasource_name,
            "type": "sql",
            "columns": all_columns,
            "row_count": 0,
            "tables": tables,
        }

        # Write to introspection cache for downstream toolsets
        cache_path = self._cache.introspection_path(datasource_name)
        cache_path.write_text(json.dumps(result, indent=2, default=str))

        self._audit.log(
            agent="introspect",
            tool="introspect_sql_schema",
            inputs={"datasource_name": datasource_name, "table_name": table_name},
            outputs=result,
            start_time=start,
        )
        return result

    async def detect_schema_drift(self, datasource_name: str) -> dict:
        """Compare current datasource structure against cached introspection.

        Performs a fresh introspection and diffs against the most recent
        cached result. Reports added columns, removed columns, type changes,
        nullability changes, enumeration changes, and relationship changes.

        Works with all datasource types (SQL, CSV, JSON, MongoDB, and
        future Notion, Sheets, Airtable) because it operates on the
        standardized 13-field column format.

        Args:
            datasource_name: Name of a configured datasource (from config).

        Returns:
            Dict with datasource, drift_detected (bool), added_columns,
            removed_columns, type_changes, nullability_changes,
            enumeration_changes, relationship_changes, and
            previous_introspection_timestamp.

        Side Effect:
            Saves previous introspection as {datasource_name}.prev.json.
            Updates the cached introspection with the current result.
            Logs via AuditLogger.
        """
        start = time.monotonic()
        ds = self._get_datasource(datasource_name)
        cache_path = self._cache.introspection_path(datasource_name)

        # Load previous introspection (if exists)
        previous: dict | None = None
        previous_timestamp = ""
        if self._cache.is_cached(cache_path):
            previous = json.loads(cache_path.read_text())
            # Preserve file modification time as timestamp
            stat = cache_path.stat()
            previous_timestamp = datetime.fromtimestamp(
                stat.st_mtime, tz=timezone.utc
            ).isoformat()
            # Save backup
            prev_path = cache_path.with_suffix(".prev.json")
            shutil.copy2(cache_path, prev_path)

        # Run fresh introspection based on datasource type
        if ds.type == "sql":
            current = await self.introspect_sql_schema(datasource_name)
        elif ds.type == "csv":
            current = await self.introspect_csv(datasource_name)
        elif ds.type == "json":
            current = await self.introspect_json(datasource_name)
        elif ds.type == "mongodb":
            current = await self.introspect_mongodb(datasource_name)
        else:
            raise ValueError(
                f"Datasource type '{ds.type}' not yet supported for drift detection. "
                f"Supported: sql, csv, json, mongodb"
            )

        # If no previous introspection, return baseline (no drift)
        if previous is None:
            result = {
                "datasource": datasource_name,
                "drift_detected": False,
                "message": "No previous introspection cached. Current result saved as baseline.",
                "added_columns": [],
                "removed_columns": [],
                "type_changes": [],
                "nullability_changes": [],
                "enumeration_changes": [],
                "relationship_changes": [],
                "previous_introspection_timestamp": "",
                "column_count": len(current.get("columns", [])),
            }
            self._audit.log(
                agent="introspect",
                tool="detect_schema_drift",
                inputs={"datasource_name": datasource_name},
                outputs=result,
                start_time=start,
            )
            return result

        # Build column lookup maps by name
        old_cols = {c["name"]: c for c in previous.get("columns", [])}
        new_cols = {c["name"]: c for c in current.get("columns", [])}

        old_names = set(old_cols.keys())
        new_names = set(new_cols.keys())

        # Detect added and removed columns
        added = [
            {"name": n, "data_type": new_cols[n].get("data_type", "?")}
            for n in sorted(new_names - old_names)
        ]
        removed = [
            {"name": n, "data_type": old_cols[n].get("data_type", "?")}
            for n in sorted(old_names - new_names)
        ]

        # Detect changes in shared columns
        type_changes = []
        nullability_changes = []
        enumeration_changes = []
        relationship_changes = []

        for name in sorted(old_names & new_names):
            old = old_cols[name]
            new = new_cols[name]

            # Type change
            old_type = old.get("data_type", "")
            new_type = new.get("data_type", "")
            if old_type != new_type:
                change = {"name": name, "old_type": old_type, "new_type": new_type}
                # Include native type info from metadata if available
                old_meta = old.get("metadata", {})
                new_meta = new.get("metadata", {})
                for key in ("notion_property_type", "airtable_field_type", "sql_type", "bson_type"):
                    if key in old_meta or key in new_meta:
                        change[f"old_{key}"] = old_meta.get(key, "")
                        change[f"new_{key}"] = new_meta.get(key, "")
                type_changes.append(change)

            # Nullability change
            old_nullable = old.get("nullable")
            new_nullable = new.get("nullable")
            if old_nullable is not None and new_nullable is not None and old_nullable != new_nullable:
                nullability_changes.append({
                    "name": name,
                    "old_nullable": old_nullable,
                    "new_nullable": new_nullable,
                })

            # Enumeration change (select options added/removed — critical for Notion/Airtable)
            old_enum = old.get("enumeration") or {}
            new_enum = new.get("enumeration") or {}
            if old_enum != new_enum:
                old_keys = set(old_enum.keys()) if isinstance(old_enum, dict) else set()
                new_keys = set(new_enum.keys()) if isinstance(new_enum, dict) else set()
                enumeration_changes.append({
                    "name": name,
                    "added_options": sorted(new_keys - old_keys),
                    "removed_options": sorted(old_keys - new_keys),
                })

            # Relationship change (linked records/relations — Notion, Airtable, SQL FK)
            old_rel = old.get("relationships", "")
            new_rel = new.get("relationships", "")
            if old_rel != new_rel:
                relationship_changes.append({
                    "name": name,
                    "old_relationships": old_rel,
                    "new_relationships": new_rel,
                })

        drift_detected = bool(
            added or removed or type_changes or nullability_changes
            or enumeration_changes or relationship_changes
        )

        result = {
            "datasource": datasource_name,
            "drift_detected": drift_detected,
            "added_columns": added,
            "removed_columns": removed,
            "type_changes": type_changes,
            "nullability_changes": nullability_changes,
            "enumeration_changes": enumeration_changes,
            "relationship_changes": relationship_changes,
            "previous_introspection_timestamp": previous_timestamp,
            "column_count": len(new_cols),
        }

        self._audit.log(
            agent="introspect",
            tool="detect_schema_drift",
            inputs={"datasource_name": datasource_name},
            outputs=result,
            start_time=start,
        )

        # Send notification if drift detected and channels configured
        if drift_detected and self._config.notifications:
            from sdc_agents.common.notify import Notifier

            changes = []
            if added:
                changes.append(f"{len(added)} added")
            if removed:
                changes.append(f"{len(removed)} removed")
            if type_changes:
                changes.append(f"{len(type_changes)} type changes")
            if nullability_changes:
                changes.append(f"{len(nullability_changes)} nullability changes")
            if enumeration_changes:
                changes.append(f"{len(enumeration_changes)} enum changes")
            if relationship_changes:
                changes.append(f"{len(relationship_changes)} relationship changes")

            notifier = Notifier(self._config)
            await notifier.send(
                event="schema_drift_detected",
                summary=f"Schema drift in '{datasource_name}': {', '.join(changes)}",
                details={
                    "agent": "introspect",
                    "tool": "detect_schema_drift",
                    "datasource": datasource_name,
                    "drift_detected": True,
                    "changes": changes,
                },
            )

        return result

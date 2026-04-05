"""Data annotations for SDC Agents SMB.

Records datasource-specific quirks discovered by agents or noted by users
that persist across sessions. Annotations are stored per-datasource as
append-only JSONL and automatically merged into introspection results.

Annotation categories:
- null_violation: Column has nulls despite schema constraint
- type_mismatch: Sample values don't match declared/inferred type
- mixed_format: Column contains values in multiple formats
- value_anomaly: Unexpected values (e.g., 'N/A' in numeric column)
- relationship_note: Clarification about linked records or relations
- data_boundary: Row/range limits (e.g., summary rows to exclude)
- user_note: Free-form annotation from user
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional


ANNOTATION_CATEGORIES = (
    "null_violation",
    "type_mismatch",
    "mixed_format",
    "value_anomaly",
    "relationship_note",
    "data_boundary",
    "user_note",
)


class AnnotationStore:
    """Manages per-datasource annotation storage and retrieval."""

    def __init__(self, cache_root: str | Path = ".sdc-cache"):
        self._root = Path(cache_root) / "annotations"
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, datasource_name: str) -> Path:
        return self._root / f"{datasource_name}.jsonl"

    def add(
        self,
        datasource_name: str,
        column: str,
        category: str,
        message: str,
        source: Literal["agent", "user"] = "agent",
    ) -> dict:
        """Add an annotation for a datasource column.

        Args:
            datasource_name: Name of the datasource.
            column: Column name the annotation applies to.
            category: Annotation category (see module docstring).
            message: Human-readable annotation text.
            source: Who created this — "agent" (automatic) or "user" (manual).

        Returns:
            The annotation record that was written.
        """
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "datasource": datasource_name,
            "column": column,
            "category": category,
            "message": message,
            "source": source,
        }

        path = self._path(datasource_name)
        with open(path, "a") as f:
            f.write(json.dumps(record) + "\n")

        return record

    def get(
        self,
        datasource_name: str,
        column: Optional[str] = None,
    ) -> list[dict]:
        """Get annotations for a datasource, optionally filtered by column.

        Args:
            datasource_name: Name of the datasource.
            column: If provided, only return annotations for this column.

        Returns:
            List of annotation records, most recent last.
        """
        path = self._path(datasource_name)
        if not path.exists():
            return []

        records = []
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                if column and record.get("column") != column:
                    continue
                records.append(record)
            except json.JSONDecodeError:
                continue

        return records

    def get_by_column(self, datasource_name: str) -> dict[str, list[dict]]:
        """Get annotations grouped by column name.

        Args:
            datasource_name: Name of the datasource.

        Returns:
            Dict mapping column names to lists of annotation records.
        """
        by_column: dict[str, list[dict]] = {}
        for record in self.get(datasource_name):
            col = record.get("column", "")
            by_column.setdefault(col, []).append(record)
        return by_column

    def clear(self, datasource_name: str) -> int:
        """Clear all annotations for a datasource.

        Args:
            datasource_name: Name of the datasource.

        Returns:
            Number of annotations that were cleared.
        """
        path = self._path(datasource_name)
        if not path.exists():
            return 0

        count = len(path.read_text().splitlines())
        path.unlink()
        return count

    def list_datasources(self) -> list[str]:
        """List datasources that have annotations.

        Returns:
            List of datasource names with annotation files.
        """
        return sorted(p.stem for p in self._root.glob("*.jsonl"))


def auto_annotate_introspection(
    store: AnnotationStore,
    datasource_name: str,
    introspection_result: dict,
) -> list[dict]:
    """Scan introspection results for anomalies and create annotations.

    Detects:
    - Null violations: column marked not-nullable but sample values contain empties
    - Type mismatches: sample values inconsistent with inferred type
    - Mixed formats: date/number columns with multiple format patterns
    - Value anomalies: sentinel values like 'N/A', 'NULL', '#N/A' in typed columns

    Args:
        store: AnnotationStore to write annotations to.
        datasource_name: Name of the datasource.
        introspection_result: Dict from an introspect_* tool.

    Returns:
        List of new annotation records created.
    """
    new_annotations = []
    columns = introspection_result.get("columns", [])

    for col in columns:
        col_name = col.get("name", "")
        data_type = col.get("data_type", "string")
        nullable = col.get("nullable")
        sample_values = col.get("sample_values", [])

        if not sample_values:
            continue

        str_samples = [str(v) for v in sample_values if v is not None]

        # Null violation: not-nullable but has empty/None values
        if nullable is False:
            empty_count = sum(
                1 for v in sample_values
                if v is None or (isinstance(v, str) and not v.strip())
            )
            if empty_count > 0:
                ann = store.add(
                    datasource_name,
                    col_name,
                    "null_violation",
                    f"Column marked not-nullable but {empty_count}/{len(sample_values)} "
                    f"sample values are empty/null",
                    source="agent",
                )
                new_annotations.append(ann)

        # Value anomaly: sentinel values in typed columns
        if data_type not in ("string", "array", "object"):
            sentinels = {"n/a", "na", "null", "none", "#n/a", "-", "--", ".", ""}
            found_sentinels = [
                v for v in str_samples
                if v.strip().lower() in sentinels
            ]
            if found_sentinels:
                ann = store.add(
                    datasource_name,
                    col_name,
                    "value_anomaly",
                    f"Column typed as '{data_type}' contains sentinel values: "
                    f"{found_sentinels[:3]}. These may cause mapping/validation errors.",
                    source="agent",
                )
                new_annotations.append(ann)

        # Mixed format: dates with multiple patterns
        if data_type in ("date", "datetime"):
            import re
            iso_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}")
            us_pattern = re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4}")
            eu_pattern = re.compile(r"^\d{1,2}\.\d{1,2}\.\d{2,4}")

            formats_found = set()
            for v in str_samples:
                v = v.strip()
                if iso_pattern.match(v):
                    formats_found.add("ISO")
                elif us_pattern.match(v):
                    formats_found.add("US")
                elif eu_pattern.match(v):
                    formats_found.add("EU")

            if len(formats_found) > 1:
                ann = store.add(
                    datasource_name,
                    col_name,
                    "mixed_format",
                    f"Date column contains multiple formats: {', '.join(sorted(formats_found))}. "
                    f"Standardize before mapping.",
                    source="agent",
                )
                new_annotations.append(ann)

        # Type mismatch: numeric column with non-numeric samples
        if data_type in ("integer", "decimal"):
            import re
            non_numeric = [
                v for v in str_samples
                if v.strip() and not re.match(r"^-?\d+\.?\d*$", v.strip())
            ]
            if non_numeric and len(non_numeric) <= len(str_samples) // 2:
                ann = store.add(
                    datasource_name,
                    col_name,
                    "type_mismatch",
                    f"Column typed as '{data_type}' but {len(non_numeric)}/{len(str_samples)} "
                    f"samples are non-numeric: {non_numeric[:3]}",
                    source="agent",
                )
                new_annotations.append(ann)

    return new_annotations


def merge_annotations_into_result(
    store: AnnotationStore,
    datasource_name: str,
    introspection_result: dict,
) -> dict:
    """Merge stored annotations into an introspection result.

    Adds an 'annotations' list to each column's metadata dict.

    Args:
        store: AnnotationStore to read from.
        datasource_name: Name of the datasource.
        introspection_result: Dict from an introspect_* tool (modified in place).

    Returns:
        The modified introspection_result.
    """
    by_column = store.get_by_column(datasource_name)

    for col in introspection_result.get("columns", []):
        col_name = col.get("name", "")
        annotations = by_column.get(col_name, [])
        if annotations:
            metadata = col.get("metadata", {})
            metadata["annotations"] = [
                {
                    "category": a["category"],
                    "message": a["message"],
                    "source": a["source"],
                    "timestamp": a["timestamp"],
                }
                for a in annotations
            ]
            col["metadata"] = metadata

    return introspection_result

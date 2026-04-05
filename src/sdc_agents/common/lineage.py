"""Cross-datasource lineage tracking for SDC Agents SMB.

Tracks data flow across agent pipeline steps: source datasource →
introspection → mapping → generation → validation → distribution.
Each step records input and output artifact paths with a lineage ID
chain for full traceability.

Stored as append-only JSONL at .sdc-cache/lineage.jsonl.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class LineageLogger:
    """Tracks data flow across agent pipeline steps."""

    def __init__(self, path: str | Path = ".sdc-cache/lineage.jsonl"):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    def log_step(
        self,
        *,
        step: str,
        agent: str,
        tool: str,
        input_artifacts: list[str],
        output_artifacts: list[str],
        datasource: str = "",
        row_index: int | None = None,
        parent_lineage_id: str = "",
    ) -> str:
        """Log a lineage step. Returns the generated lineage_id.

        Args:
            step: Pipeline step name (e.g., "generate", "validate", "distribute").
            agent: Agent name that performed this step.
            tool: Tool function name.
            input_artifacts: Paths to input files consumed by this step.
            output_artifacts: Paths to output files produced by this step.
            datasource: Name of the originating datasource (if applicable).
            row_index: Row index in the datasource (if applicable).
            parent_lineage_id: Lineage ID of the preceding step (if chained).

        Returns:
            Generated lineage_id for this step.
        """
        lineage_id = f"lin_{uuid.uuid4().hex[:12]}"

        record = {
            "lineage_id": lineage_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "step": step,
            "agent": agent,
            "tool": tool,
            "input_artifacts": input_artifacts,
            "output_artifacts": output_artifacts,
            "datasource": datasource,
            "row_index": row_index,
            "parent_lineage_id": parent_lineage_id,
        }

        line = json.dumps(record, default=str) + "\n"
        with open(self._path, "a") as f:
            f.write(line)

        return lineage_id

    def trace(self, artifact_path: str) -> list[dict]:
        """Trace an artifact back through the lineage chain.

        Finds all lineage records where the artifact appears in
        output_artifacts, then follows parent_lineage_id links
        backwards to the source.

        Args:
            artifact_path: Path to the artifact to trace.

        Returns:
            List of lineage records forming the chain from source
            to the given artifact, ordered oldest-first.
        """
        if not self._path.exists():
            return []

        # Build lookup maps
        all_records: dict[str, dict] = {}
        output_to_ids: dict[str, list[str]] = {}

        for line in self._path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                lid = record.get("lineage_id", "")
                all_records[lid] = record
                for out_path in record.get("output_artifacts", []):
                    output_to_ids.setdefault(out_path, []).append(lid)
            except json.JSONDecodeError:
                continue

        # Find lineage IDs that produced this artifact
        matching_ids = output_to_ids.get(artifact_path, [])
        if not matching_ids:
            return []

        # Walk the chain backwards from each match
        chain: list[dict] = []
        visited: set[str] = set()

        def _walk(lid: str) -> None:
            if lid in visited or lid not in all_records:
                return
            visited.add(lid)
            record = all_records[lid]
            parent = record.get("parent_lineage_id", "")
            if parent:
                _walk(parent)
            chain.append(record)

        for lid in matching_ids:
            _walk(lid)

        return chain

    def get_records(
        self,
        datasource: str | None = None,
        agent: str | None = None,
        limit: int = 500,
    ) -> list[dict]:
        """Read lineage records with optional filters.

        Args:
            datasource: Filter by originating datasource name.
            agent: Filter by agent name.
            limit: Maximum records to return.

        Returns:
            List of lineage record dicts, most recent last.
        """
        if not self._path.exists():
            return []

        records = []
        for line in self._path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            if datasource and record.get("datasource") != datasource:
                continue
            if agent and record.get("agent") != agent:
                continue

            records.append(record)

        return records[-limit:]

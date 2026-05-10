"""Compliance report generator for SDC Agents SMB.

Reads audit.jsonl and lineage.jsonl to produce structured compliance
evidence: data access summaries, tool invocation counts, credential
access patterns, data flow traces, error logs, and validation results.

Output formats: JSON, Markdown, HTML.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal


class ComplianceReporter:
    """Generates compliance reports from audit and lineage logs."""

    def __init__(
        self,
        audit_path: str | Path = ".sdc-cache/audit.jsonl",
        lineage_path: str | Path = ".sdc-cache/lineage.jsonl",
    ):
        self._audit_path = Path(audit_path)
        self._lineage_path = Path(lineage_path)

    def generate(
        self,
        *,
        last_hours: int | None = None,
        last_days: int | None = None,
        output_format: Literal["json", "markdown", "html"] = "json",
    ) -> str:
        """Generate a compliance report.

        Args:
            last_hours: Include records from the last N hours.
            last_days: Include records from the last N days.
            output_format: Output format — "json", "markdown", or "html".

        Returns:
            Report content as a string.
        """
        cutoff = None
        if last_days:
            cutoff = datetime.now(timezone.utc) - timedelta(days=last_days)
        elif last_hours:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=last_hours)

        audit_records = self._read_audit(cutoff)
        lineage_records = self._read_lineage(cutoff)

        report = self._build_report(audit_records, lineage_records, cutoff)

        if output_format == "markdown":
            return self._render_markdown(report)
        elif output_format == "html":
            return self._render_html(report)
        return json.dumps(report, indent=2, default=str)

    def _read_audit(self, cutoff: datetime | None) -> list[dict]:
        """Read and filter audit records."""
        if not self._audit_path.exists():
            return []

        records = []
        for line in self._audit_path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            if cutoff:
                try:
                    ts = datetime.fromisoformat(record.get("timestamp", ""))
                    if ts < cutoff:
                        continue
                except (ValueError, TypeError):
                    continue

            records.append(record)
        return records

    def _read_lineage(self, cutoff: datetime | None) -> list[dict]:
        """Read and filter lineage records."""
        if not self._lineage_path.exists():
            return []

        records = []
        for line in self._lineage_path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            if cutoff:
                try:
                    ts = datetime.fromisoformat(record.get("timestamp", ""))
                    if ts < cutoff:
                        continue
                except (ValueError, TypeError):
                    continue

            records.append(record)
        return records

    def _build_report(
        self,
        audit_records: list[dict],
        lineage_records: list[dict],
        cutoff: datetime | None,
    ) -> dict:
        """Build the structured report from raw records."""
        # 1. Data Access Summary
        datasource_access: dict[str, dict] = {}
        for r in audit_records:
            inputs = r.get("inputs", {})
            if isinstance(inputs, dict):
                ds = inputs.get("datasource_name", inputs.get("datasource", ""))
                if ds:
                    if ds not in datasource_access:
                        datasource_access[ds] = {"agent": set(), "count": 0}
                    datasource_access[ds]["agent"].add(r.get("agent", "?"))
                    datasource_access[ds]["count"] += 1

        data_access = [
            {
                "datasource": ds,
                "agents": sorted(info["agent"]),
                "access_count": info["count"],
            }
            for ds, info in sorted(datasource_access.items())
        ]

        # 2. Tool Invocation Counts
        by_agent_tool: dict[str, dict] = {}
        total_duration = 0.0
        error_count = 0
        for r in audit_records:
            key = f"{r.get('agent', '?')}.{r.get('tool', '?')}"
            if key not in by_agent_tool:
                by_agent_tool[key] = {"count": 0, "total_duration_ms": 0.0, "errors": 0}
            by_agent_tool[key]["count"] += 1
            dur = r.get("duration_ms", 0)
            by_agent_tool[key]["total_duration_ms"] += dur
            total_duration += dur

            # Detect errors from outputs
            outputs = r.get("outputs", {})
            if isinstance(outputs, dict):
                if outputs.get("status") in ("failed", "error"):
                    by_agent_tool[key]["errors"] += 1
                    error_count += 1

        tool_counts = [
            {
                "agent_tool": key,
                "count": info["count"],
                "avg_duration_ms": round(info["total_duration_ms"] / info["count"], 2),
                "errors": info["errors"],
            }
            for key, info in sorted(by_agent_tool.items())
        ]

        # 3. Credential Access Patterns
        credential_tools = set()
        for r in audit_records:
            inputs = r.get("inputs", {})
            if isinstance(inputs, dict):
                for key in inputs:
                    if inputs[key] == "***REDACTED***":
                        credential_tools.add(f"{r.get('agent', '?')}.{r.get('tool', '?')}")

        # 4. Data Flow (from lineage)
        data_flows = []
        seen_flows: set[str] = set()
        for r in lineage_records:
            flow_key = f"{r.get('step', '')}:{','.join(r.get('input_artifacts', []))}"
            if flow_key not in seen_flows:
                seen_flows.add(flow_key)
                data_flows.append(
                    {
                        "step": r.get("step", ""),
                        "agent": r.get("agent", ""),
                        "tool": r.get("tool", ""),
                        "datasource": r.get("datasource", ""),
                        "inputs": r.get("input_artifacts", []),
                        "outputs": r.get("output_artifacts", []),
                    }
                )

        # 5. Errors
        errors = []
        for r in audit_records:
            outputs = r.get("outputs", {})
            if isinstance(outputs, dict) and outputs.get("status") in ("failed", "error"):
                errors.append(
                    {
                        "timestamp": r.get("timestamp", ""),
                        "agent": r.get("agent", ""),
                        "tool": r.get("tool", ""),
                        "inputs": r.get("inputs", {}),
                        "error": outputs.get("error", outputs.get("message", "")),
                    }
                )

        # 6. Validation Results
        validation_records = [
            r
            for r in audit_records
            if r.get("agent") == "validation"
            and r.get("tool") in ("validate_instance", "validate_batch")
        ]
        validation_total = len(validation_records)
        validation_passed = sum(
            1
            for r in validation_records
            if isinstance(r.get("outputs", {}), dict) and r["outputs"].get("valid", False)
        )

        period_start = cutoff.isoformat() if cutoff else "(all time)"
        period_end = datetime.now(timezone.utc).isoformat()

        return {
            "report_type": "compliance",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "period": {"start": period_start, "end": period_end},
            "summary": {
                "total_audit_records": len(audit_records),
                "total_lineage_records": len(lineage_records),
                "total_errors": error_count,
                "avg_duration_ms": (
                    round(total_duration / len(audit_records), 2) if audit_records else 0
                ),
            },
            "data_access": data_access,
            "tool_invocations": tool_counts,
            "credential_access": sorted(credential_tools),
            "data_flows": data_flows,
            "errors": errors,
            "validation": {
                "total": validation_total,
                "passed": validation_passed,
                "failed": validation_total - validation_passed,
                "pass_rate": (
                    round(validation_passed / validation_total * 100, 1) if validation_total else 0
                ),
            },
        }

    def _render_markdown(self, report: dict) -> str:
        """Render report as Markdown."""
        lines = [
            "# SDC Agents SMB — Compliance Report",
            "",
            f"**Generated:** {report['generated_at']}",
            f"**Period:** {report['period']['start']} to {report['period']['end']}",
            "",
            "## Summary",
            "",
            f"- Audit records: {report['summary']['total_audit_records']}",
            f"- Lineage records: {report['summary']['total_lineage_records']}",
            f"- Total errors: {report['summary']['total_errors']}",
            f"- Avg duration: {report['summary']['avg_duration_ms']}ms",
            "",
            "## Data Access",
            "",
            "| Datasource | Agents | Access Count |",
            "|---|---|---|",
        ]
        for da in report["data_access"]:
            lines.append(
                f"| {da['datasource']} | {', '.join(da['agents'])} | {da['access_count']} |"
            )

        lines.extend(
            [
                "",
                "## Tool Invocations",
                "",
                "| Agent.Tool | Count | Avg Duration | Errors |",
                "|---|---|---|---|",
            ]
        )
        for ti in report["tool_invocations"]:
            lines.append(
                f"| {ti['agent_tool']} | {ti['count']} | "
                f"{ti['avg_duration_ms']}ms | {ti['errors']} |"
            )

        lines.extend(
            [
                "",
                "## Credential Access",
                "",
            ]
        )
        if report["credential_access"]:
            for ca in report["credential_access"]:
                lines.append(f"- {ca}")
        else:
            lines.append("No credential access detected in audit period.")

        lines.extend(
            [
                "",
                "## Data Flow",
                "",
            ]
        )
        for df in report["data_flows"]:
            inputs = ", ".join(df["inputs"]) or "(none)"
            outputs = ", ".join(df["outputs"]) or "(none)"
            lines.append(f"- **{df['step']}** ({df['agent']}.{df['tool']}): {inputs} → {outputs}")

        lines.extend(
            [
                "",
                "## Validation Results",
                "",
                f"- Total: {report['validation']['total']}",
                f"- Passed: {report['validation']['passed']}",
                f"- Failed: {report['validation']['failed']}",
                f"- Pass rate: {report['validation']['pass_rate']}%",
                "",
                "## Errors",
                "",
            ]
        )
        if report["errors"]:
            for err in report["errors"]:
                lines.append(
                    f"- **{err['timestamp']}** " f"{err['agent']}.{err['tool']}: {err['error']}"
                )
        else:
            lines.append("No errors in audit period.")

        return "\n".join(lines)

    def _render_html(self, report: dict) -> str:
        """Render report as self-contained HTML."""
        md = self._render_markdown(report)
        # Simple HTML wrapper — production would use a proper template

        # Convert markdown tables to HTML tables (basic)
        html_body = ""
        in_table = False
        for line in md.split("\n"):
            if line.startswith("|") and "---|" not in line:
                cells = [c.strip() for c in line.split("|")[1:-1]]
                if not in_table:
                    html_body += (
                        "<table style='border-collapse:collapse;width:100%;margin:16px 0'>\n"
                    )
                    html_body += (
                        "<tr>"
                        + "".join(
                            f"<th style='text-align:left;padding:8px;"
                            f"border:1px solid #334155;background:#1e293b'>{c}</th>"
                            for c in cells
                        )
                        + "</tr>\n"
                    )
                    in_table = True
                else:
                    html_body += (
                        "<tr>"
                        + "".join(
                            f"<td style='padding:8px;border:1px solid #334155'>{c}</td>"
                            for c in cells
                        )
                        + "</tr>\n"
                    )
            elif line.startswith("|---"):
                continue
            else:
                if in_table:
                    html_body += "</table>\n"
                    in_table = False
                if line.startswith("# "):
                    html_body += f"<h1>{line[2:]}</h1>\n"
                elif line.startswith("## "):
                    html_body += (
                        f"<h2 style='margin-top:24px;"
                        f"border-bottom:1px solid #334155;"
                        f"padding-bottom:8px'>{line[3:]}</h2>\n"
                    )
                elif line.startswith("- **"):
                    html_body += f"<p style='margin:4px 0'>{line[2:]}</p>\n"
                elif line.startswith("- "):
                    html_body += f"<p style='margin:4px 0;padding-left:16px'>{line[2:]}</p>\n"
                elif line.startswith("**"):
                    html_body += f"<p><strong>{line}</strong></p>\n"
                elif line.strip():
                    html_body += f"<p>{line}</p>\n"
        if in_table:
            html_body += "</table>\n"

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>SDC Agents SMB — Compliance Report</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         background: #0f172a; color: #e2e8f0; padding: 40px; max-width: 900px; margin: 0 auto; }}
  h1 {{ color: #38bdf8; }}
  h2 {{ color: #94a3b8; }}
  table {{ font-size: 14px; }}
  th {{ color: #94a3b8; }}
</style>
</head>
<body>
{html_body}
<p style="color:#64748b;font-size:12px;margin-top:40px">
  Generated by SDC Agents SMB Compliance Reporter
</p>
</body>
</html>"""

"""Audit dashboard for SDC Agents SMB.

Lightweight web UI for browsing, filtering, and visualizing the
append-only audit log. Reads .sdc-cache/audit.jsonl directly —
no external database required.

Requires optional dependencies: pip install sdc-agents-smb[dashboard]
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    from fastapi import FastAPI, Query
    from fastapi.responses import HTMLResponse, JSONResponse
except ImportError:
    raise ImportError(
        "FastAPI is required for the audit dashboard. "
        "Install with: pip install sdc-agents-smb[dashboard]"
    )

app = FastAPI(title="SDC Agents SMB — Audit Dashboard", version="4.0.0")

# Set by CLI before uvicorn.run()
_audit_path: str = ".sdc-cache/audit.jsonl"


def _read_records(
    agent: Optional[str] = None,
    tool: Optional[str] = None,
    last_hours: Optional[int] = None,
    limit: int = 200,
) -> list[dict]:
    """Read and filter audit records from JSONL file."""
    path = Path(_audit_path)
    if not path.exists():
        return []

    cutoff = None
    if last_hours:
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(hours=last_hours)

    records = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue

        if agent and record.get("agent") != agent:
            continue
        if tool and record.get("tool") != tool:
            continue
        if cutoff:
            try:
                ts = datetime.fromisoformat(record.get("timestamp", ""))
                if ts < cutoff:
                    continue
            except (ValueError, TypeError):
                continue

        records.append(record)

    return records[-limit:]


def _aggregate(records: list[dict]) -> dict:
    """Compute aggregate statistics from audit records."""
    by_agent: dict[str, int] = {}
    by_tool: dict[str, int] = {}
    total_duration = 0.0

    for r in records:
        agent = r.get("agent", "?")
        tool = r.get("tool", "?")
        by_agent[agent] = by_agent.get(agent, 0) + 1
        by_tool[tool] = by_tool.get(tool, 0) + 1
        total_duration += r.get("duration_ms", 0)

    return {
        "total_records": len(records),
        "by_agent": by_agent,
        "by_tool": by_tool,
        "avg_duration_ms": round(total_duration / len(records), 2) if records else 0,
    }


@app.get("/api/records")
async def get_records(
    agent: Optional[str] = Query(None),
    tool: Optional[str] = Query(None),
    last_hours: Optional[int] = Query(None),
    limit: int = Query(200),
) -> JSONResponse:
    """Return filtered audit records as JSON."""
    records = _read_records(agent=agent, tool=tool, last_hours=last_hours, limit=limit)
    return JSONResponse({"records": records, "count": len(records)})


@app.get("/api/aggregate")
async def get_aggregate(
    last_hours: Optional[int] = Query(None),
) -> JSONResponse:
    """Return aggregate statistics as JSON."""
    records = _read_records(last_hours=last_hours, limit=10000)
    return JSONResponse(_aggregate(records))


@app.get("/api/export")
async def export_records(
    agent: Optional[str] = Query(None),
    tool: Optional[str] = Query(None),
    last_hours: Optional[int] = Query(None),
    format: str = Query("json"),
) -> JSONResponse:
    """Export filtered records as JSON or CSV."""
    records = _read_records(agent=agent, tool=tool, last_hours=last_hours, limit=10000)

    if format == "csv":
        import csv
        import io
        output = io.StringIO()
        if records:
            writer = csv.DictWriter(output, fieldnames=["timestamp", "agent", "tool", "duration_ms"])
            writer.writeheader()
            for r in records:
                writer.writerow({
                    "timestamp": r.get("timestamp", ""),
                    "agent": r.get("agent", ""),
                    "tool": r.get("tool", ""),
                    "duration_ms": r.get("duration_ms", ""),
                })
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(output.getvalue(), media_type="text/csv")

    return JSONResponse({"records": records, "count": len(records)})


@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the dashboard HTML page."""
    return _DASHBOARD_HTML


_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SDC Agents SMB — Audit Dashboard</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         background: #0f172a; color: #e2e8f0; padding: 20px; }
  h1 { color: #38bdf8; margin-bottom: 20px; font-size: 1.5rem; }
  .filters { display: flex; gap: 12px; margin-bottom: 20px; flex-wrap: wrap; }
  .filters select, .filters input, .filters button {
    padding: 8px 12px; border: 1px solid #334155; border-radius: 6px;
    background: #1e293b; color: #e2e8f0; font-size: 14px; }
  .filters button { background: #2563eb; border-color: #2563eb; cursor: pointer; }
  .filters button:hover { background: #1d4ed8; }
  .stats { display: flex; gap: 16px; margin-bottom: 20px; flex-wrap: wrap; }
  .stat { background: #1e293b; padding: 16px 20px; border-radius: 8px; min-width: 150px; }
  .stat .label { font-size: 12px; color: #94a3b8; text-transform: uppercase; }
  .stat .value { font-size: 24px; font-weight: bold; color: #38bdf8; margin-top: 4px; }
  table { width: 100%; border-collapse: collapse; }
  th { text-align: left; padding: 10px 12px; background: #1e293b; color: #94a3b8;
       font-size: 12px; text-transform: uppercase; border-bottom: 2px solid #334155; }
  td { padding: 10px 12px; border-bottom: 1px solid #1e293b; font-size: 14px; }
  tr:hover { background: #1e293b; }
  .agent-tag { padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; }
  .agent-introspect { background: #166534; color: #86efac; }
  .agent-catalog { background: #1e3a5f; color: #7dd3fc; }
  .agent-validation { background: #713f12; color: #fde047; }
  .agent-distribution { background: #581c87; color: #d8b4fe; }
  .agent-assembly { background: #7f1d1d; color: #fca5a5; }
  .agent-mapping { background: #164e63; color: #67e8f9; }
  .agent-generator { background: #365314; color: #bef264; }
  .agent-knowledge { background: #4a1d96; color: #c4b5fd; }
  .agent-scheduler { background: #44403c; color: #d6d3d1; }
  .agent-notifier { background: #44403c; color: #d6d3d1; }
  .export-links { margin-top: 16px; }
  .export-links a { color: #38bdf8; margin-right: 16px; text-decoration: none; }
  .export-links a:hover { text-decoration: underline; }
</style>
</head>
<body>
<h1>SDC Agents SMB — Audit Dashboard</h1>

<div class="filters">
  <select id="agentFilter">
    <option value="">All agents</option>
    <option>assembly</option><option>catalog</option><option>distribution</option>
    <option>generator</option><option>introspect</option><option>knowledge</option>
    <option>mapping</option><option>validation</option><option>scheduler</option>
    <option>notifier</option>
  </select>
  <select id="hoursFilter">
    <option value="">All time</option>
    <option value="1">Last 1 hour</option>
    <option value="6">Last 6 hours</option>
    <option value="24">Last 24 hours</option>
    <option value="168">Last 7 days</option>
    <option value="720">Last 30 days</option>
  </select>
  <input id="toolFilter" type="text" placeholder="Filter by tool name...">
  <button onclick="loadData()">Apply</button>
</div>

<div class="stats" id="stats"></div>

<div class="export-links" id="exportLinks"></div>

<table>
  <thead>
    <tr><th>Timestamp</th><th>Agent</th><th>Tool</th><th>Duration</th><th>Inputs</th></tr>
  </thead>
  <tbody id="records"></tbody>
</table>

<script>
async function loadData() {
  const agent = document.getElementById('agentFilter').value;
  const hours = document.getElementById('hoursFilter').value;
  const tool = document.getElementById('toolFilter').value;

  let url = '/api/records?limit=500';
  if (agent) url += '&agent=' + agent;
  if (hours) url += '&last_hours=' + hours;
  if (tool) url += '&tool=' + tool;

  const resp = await fetch(url);
  const data = await resp.json();

  // Stats
  const aggUrl = '/api/aggregate' + (hours ? '?last_hours=' + hours : '');
  const aggResp = await fetch(aggUrl);
  const agg = await aggResp.json();

  document.getElementById('stats').innerHTML = `
    <div class="stat"><div class="label">Total Records</div><div class="value">${agg.total_records}</div></div>
    <div class="stat"><div class="label">Agents</div><div class="value">${Object.keys(agg.by_agent).length}</div></div>
    <div class="stat"><div class="label">Avg Duration</div><div class="value">${agg.avg_duration_ms}ms</div></div>
  `;

  // Export links
  let exportUrl = '/api/export?format=';
  if (agent) exportUrl += '&agent=' + agent;
  if (hours) exportUrl += '&last_hours=' + hours;
  if (tool) exportUrl += '&tool=' + tool;
  document.getElementById('exportLinks').innerHTML = `
    <a href="${exportUrl}json" target="_blank">Export JSON</a>
    <a href="${exportUrl}csv" target="_blank">Export CSV</a>
  `;

  // Records table
  const tbody = document.getElementById('records');
  tbody.innerHTML = data.records.reverse().map(r => {
    const agent = r.agent || '?';
    const inputs = r.inputs ? Object.keys(r.inputs).join(', ') : '';
    const ts = r.timestamp ? r.timestamp.substring(0, 19).replace('T', ' ') : '?';
    const dur = r.duration_ms ? r.duration_ms.toFixed(1) + 'ms' : '?';
    return `<tr>
      <td>${ts}</td>
      <td><span class="agent-tag agent-${agent}">${agent}</span></td>
      <td>${r.tool || '?'}</td>
      <td>${dur}</td>
      <td style="color:#94a3b8;font-size:12px">${inputs}</td>
    </tr>`;
  }).join('');
}

loadData();
</script>
</body>
</html>
"""

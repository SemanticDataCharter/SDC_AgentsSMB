# SDC Data Integrity — OpenClaw Skill

Structured data introspection, validation, and distribution for [OpenClaw](https://github.com/openclaw/openclaw) via [SDC Agents SMB](https://github.com/SemanticDataCharter/SDC_AgentsSMB).

## What This Does

This skill gives OpenClaw users access to SDC's data integrity pipeline through their existing messaging platforms (Slack, Telegram, WhatsApp, etc.). OpenClaw handles the conversation; SDC handles the data.

**Available tools:**

| Tool | What It Does |
|---|---|
| `sdc_introspect_csv` | Analyze CSV structure: column types, nullability, sample values |
| `sdc_introspect_sql` | Introspect SQL database schema: columns, types, keys, constraints |
| `sdc_introspect_notion` | Introspect Notion database properties and relations |
| `sdc_detect_drift` | Compare current datasource structure against cached previous version |
| `sdc_validate_batch` | Validate XML instances against SDC4 schemas |
| `sdc_distribute_batch` | Distribute artifact packages to configured destinations |
| `sdc_download_package` | Download a published data model package (.zip) |
| `sdc_audit_summary` | Show recent audit log entries |
| `sdc_compliance_report` | Generate compliance report from audit/lineage logs |

## Prerequisites

1. **Python 3.11+** with SDC Agents SMB installed:
   ```bash
   pip install sdc-agents-smb
   ```

2. **sdc-agents.yaml** configured in your working directory with datasources, SDCStudio API key, etc.

3. **Node.js 18+** (for the OpenClaw bridge)

## Installation

Copy the `openclaw-sdc/` directory to your OpenClaw skills directory, or install from ClawHub (when published).

## Architecture

```
OpenClaw Gateway (Node.js)
    |
    v (tool invocation)
SDC OpenClaw Bridge (this package)
    |
    v (spawns subprocess)
sdc-agents serve --mcp <agent>
    |
    v (MCP JSON-RPC)
SDC Toolset (Python)
    |
    v
Data stores / SDCStudio APIs
```

The bridge spawns `sdc-agents serve --mcp <agent>` as subprocesses and translates between OpenClaw's tool call format and MCP's JSON-RPC protocol. MCP server processes are cached and reused across calls.

## Security

- SDC's purpose-scoped security model is preserved — the bridge calls MCP tools, not raw Python
- OpenClaw users cannot escalate beyond the declared tool set
- SDC credentials stay in `sdc-agents.yaml` on the host, not in OpenClaw's config
- All tool calls are logged to SDC's append-only audit log (`.sdc-cache/audit.jsonl`)

## Testing

```bash
cd openclaw-sdc
node src/index.js --test
```

## License

Apache License 2.0

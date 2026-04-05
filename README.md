# SDC Agents SMB

Purpose-scoped ADK agents for SDC4 data operations — **SMB Edition**.

Designed for personal and small/medium business usage. Uses a local LLM via [Ollama](https://ollama.com) instead of a Google API key, while connecting to the commercial [SDCStudio](https://sdcstudio.axius-sdc.com) SaaS backend for catalog, validation, and assembly APIs.

## Positioning

| | **SDC Agents** | **SDC Agents SMB** | **SDC Agents Sovereign** |
|---|---|---|---|
| Target | Enterprise | Personal / SMB | Air-gapped / Regulated |
| Backend | SDCStudio SaaS | SDCStudio SaaS | SDCStudioSov (local) |
| LLM | Gemini (Google API key) | Local via Ollama | Local via Ollama |
| Google API Key | Required | **Not required** | Not required |
| BigQuery | Yes | No | No |
| Vertex AI Search | Yes | No | No |
| Wallet/Billing | Yes | Yes | No (site-licensed) |

## Agents

8 purpose-scoped agents with 39+ tools (core + ToolsetHub plugins):

| Agent | Tools | Network | Datasource | Purpose |
|---|---|---|---|---|
| Catalog | 7 | HTTPS | None | Discover schemas, download artifacts and packages |
| Introspect | 6+ | None | Read-only | Extract datasource structure (SQL, CSV, JSON, MongoDB + ToolsetHub) |
| Mapping | 3 | None | None | Map columns to semantic components |
| Generator | 3 | None | Read-only | Produce XML instances from mapped data |
| Validation | 3 | HTTPS | None | Validate and sign XML via VaaS API |
| Distribution | 5 | Local | None | Route artifacts to Fuseki, Neo4j, REST, filesystem |
| Knowledge | 3 | None | Read-only | Ingest context into ChromaDB vector store |
| Assembly | 7 | HTTPS | None | Discover components, HITL review, assemble data models |

Introspect dynamically loads ToolsetHub plugins — install `[notion]`, `[sheets]`, or `[airtable]` for SMB-native datasource support.

## Features

### Core Pipeline
- **Introspect** datasources with 13-field standardized column analysis and 10 type inference patterns
- **Discover** matching catalog components with type compatibility scoring
- **HITL review gate** for billable minting operations — see costs before committing
- **Assemble** data models via the SDCStudio Assembly API (sync + async with hybrid polling)
- **Download** published data model packages (.zip with XSD, XML, JSON, JSON-LD, HTML, SHA1)
- **Generate** XML instances from mapped datasource records
- **Validate** instances against XSD 1.1 schemas via VaaS API (deterministic, not probabilistic)
- **Distribute** artifact packages to Fuseki, Neo4j, REST APIs, or filesystem

### SMB-Native Datasources (ToolsetHub)
- **Notion** — database properties, relations, rollups, select options (`pip install sdc-agents-smb[notion]`)
- **Google Sheets** — headers, inferred column types, sheet metadata (`pip install sdc-agents-smb[sheets]`)
- **Airtable** — field types, linked records, formula/lookup fields (`pip install sdc-agents-smb[airtable]`)
- Community extensible — add HubSpot, QuickBooks, Salesforce by following the reference pattern

### Automation
- **Scheduler** — cron-based pipeline automation via APScheduler (`sdc-agents schedule run`)
- **Notifications** — push status to Slack webhooks, Telegram bots, or SMTP email
- **Pipeline templates** — 7 bundled workflows (`sdc-agents pipeline run healthcare-csv -p datasource=patients`)

### Data Governance
- **Schema drift detection** — compare current structure against cached previous introspection, alerts on changes
- **Data annotations** — agents auto-detect anomalies (null violations, mixed date formats, sentinel values); users add manual notes; annotations persist across sessions and auto-merge into future introspections
- **Cross-datasource lineage** — track data flow from source through mapping, generation, validation, to distribution
- **Compliance reports** — generate JSON/Markdown/HTML evidence from audit + lineage logs (`sdc-agents compliance report`)
- **Append-only audit** — every tool call logged with credential redaction to `.sdc-cache/audit.jsonl`

### Integrations
- **MCP server mode** — serve any agent as an MCP server for Claude Desktop, Cursor, etc.
- **Audit dashboard** — web UI for browsing, filtering, and exporting audit records (`sdc-agents audit serve`)
- **OpenClaw skill** — 9-tool bridge exposing SDC tools to OpenClaw's messaging platform ecosystem

## Quick Start

### 1. Install Ollama and pull a model

```bash
# Install Ollama: https://ollama.com/download
ollama pull gemma4:26b
```

### 2. Install SDC Agents SMB

```bash
pip install sdc-agents-smb

# Optional extras:
pip install sdc-agents-smb[knowledge]                    # PDF, DOCX, ChromaDB
pip install sdc-agents-smb[notion,sheets,airtable]       # SMB datasources
pip install sdc-agents-smb[dashboard]                    # Audit dashboard web UI
```

### 3. Configure

```bash
cp sdc-agents.example.yaml sdc-agents.yaml
# Edit sdc-agents.yaml with your SDCStudio URL, API key, and datasources
```

### 4. Run

```bash
# MCP mode — serve an agent as an MCP server
sdc-agents serve --mcp catalog
sdc-agents serve --mcp introspect

# Check configuration and installed toolsets
sdc-agents info
sdc-agents toolset list
sdc-agents validate-config

# Run a pipeline template
sdc-agents pipeline list
sdc-agents pipeline run healthcare-csv -p datasource=patient_csv

# Start the scheduler
sdc-agents schedule list
sdc-agents schedule run

# View audit log and dashboard
sdc-agents audit show --last 24h
sdc-agents audit serve --port 8080

# Manage data annotations
sdc-agents annotate list-all
sdc-agents annotate add my_csv email "EU rows use comma decimal separator"

# Assembly review workflow
sdc-agents assembly list-pending
sdc-agents assembly review quarterly_model
sdc-agents assembly approve quarterly_model

# Generate compliance report
sdc-agents compliance report --format html --last 30d -o report.html
```

### 5. ADK mode (standalone agent)

```python
from sdc_agents.agents.catalog import create_catalog_agent
from sdc_agents.common.config import load_config

config = load_config("sdc-agents.yaml")
agent = create_catalog_agent(config)
# model defaults to ollama_chat/gemma4:26b from config
```

## Model Configuration

The default model is `ollama_chat/gemma4:26b`. Configure in `sdc-agents.yaml`:

```yaml
model:
  default: "ollama_chat/gemma4:26b"
  ollama_base_url: "http://localhost:11434"
```

### Tested Models

| Model | Size | Tool Calling | Notes |
|---|---|---|---|
| `gemma4:26b` | 26B MoE | Native | Recommended default |
| `qwen3.5:32b` | 32B | Native | Strong reasoning |
| `llama3.1:8b` | 8B | Native | Lightweight option |

Any Ollama model with tool-calling support should work. Use the `ollama_chat/` prefix for chat models.

## Security Model

- **Purpose scoping** — each agent has a narrow tool set, no mega-agent
- **Security isolation** — no agent has both datasource access AND network access
- **Private project enforcement** — created components go to non-public SDCStudio projects only
- **Read-only datasources** — SQL write operations rejected; all introspection is read-only
- **Credential redaction** — audit logger redacts `connection`, `token`, `key`, `password`, `secret`
- **Path confinement** — validation/distribution restricted to configured output directory
- **Append-only audit** — every tool call logged to `.sdc-cache/audit.jsonl`
- **ToolsetHub scope enforcement** — plugins declare network hosts, datasource types, and file access; violations rejected at load time

## Documentation

- [Repository Guide](docs/ecosystem/REPOSITORY_GUIDE.md) — catalog of all SDC FOSS repos
- [Architecture Overview](docs/ecosystem/ARCHITECTURE_OVERVIEW.md) — how the stack fits together
- [ClawFeatures](docs/design/ClawFeatures.md) — competitive positioning vs OpenClaw
- [PRD](docs/design/SDC_AGENTS_SMB_PRD.md) — product requirements document

## License

Apache License 2.0 — see [LICENSE](LICENSE).

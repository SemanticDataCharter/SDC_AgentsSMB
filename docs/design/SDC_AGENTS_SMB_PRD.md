# SDC Agents SMB: Roadmap PRD

**Date**: 2026-04-04
**Status**: Draft
**Author**: Timothy W. Cook / Claude Code
**Repository**: `AXiUS-SDC/SDC_AgentsSMB` (Apache 2.0 License)
**Related**: [ClawFeatures.md](ClawFeatures.md) (competitive positioning and roadmap origin), `SDC_Agents/docs/dev/SDC_AGENTS_PRD.md` (upstream agent PRD)

---

## Executive Summary

### Problem

SDC Agents SMB ships with a solid data introspection foundation: 8 purpose-scoped agents, 32 tools, MCP server mode, append-only audit logging, and local LLM inference via Ollama. This is sufficient for a developer who manually triggers pipelines from the CLI.

It is not sufficient for personal users and SMBs who need:

1. **Proactive automation** — pipelines that run on schedule without manual intervention
2. **Status visibility** — notifications when validation fails, schema changes, or distribution completes
3. **Ecosystem extensibility** — community-contributed toolsets with declared security scopes
4. **Data governance evidence** — compliance reports, lineage tracking, and drift detection

Without these capabilities, SDC Agents SMB remains a CLI toolkit. With them, it becomes a daily-use data integrity platform that complements communication-layer tools like OpenClaw.

### Solution

A 4-phase roadmap adding reach, ecosystem, and differentiation features to the existing foundation:

| Phase | Features | Outcome |
|---|---|---|
| **Phase 1 (Current)** | 8 agents, 32 tools, MCP, audit, Ollama | CLI-triggered data introspection toolkit |
| **Phase 2 (Reach)** | Notification destinations, CLI scheduler, OpenClaw skill | Proactive, integrated platform |
| **Phase 3 (Ecosystem)** | ToolsetHub, pipeline templates, audit dashboard | Extensible community-driven platform |
| **Phase 4 (Differentiation)** | Schema drift detection, lineage, compliance reports | Data governance platform |

### Value Proposition

- **For personal users**: Automated pipelines that monitor data projects without babysitting
- **For SMBs**: Compliance evidence, schema drift alerts, and audit trails that satisfy regulators
- **For the SDC ecosystem**: An on-ramp to SDCStudio SaaS that demonstrates value before enterprise commitment
- **For OpenClaw users**: A data integrity layer that handles everything OpenClaw cannot — introspection, validation, semantic mapping, and standards-based distribution

### Security Principles (Maintained)

All new features adhere to the six security principles established in the upstream SDC_AGENTS_PRD:

1. **No agent has both datasource access and network access** — notification delivery is a Distribution Agent concern (network scope), not an Introspect Agent concern (datasource scope)
2. **Read-only datasource access** — schema drift detection reads current structure and compares to cache; it never writes to datasources
3. **Tools are declarative Python functions** — scheduler invokes existing tools by name, not arbitrary code
4. **Structured audit log** — all scheduled and notification tool calls go through the existing `AuditLogger`
5. **No credential sharing** — notification credentials (`${SLACK_WEBHOOK_URL}`, `${TELEGRAM_BOT_TOKEN}`) are scoped to the Distribution Agent's config, not shared with other agents
6. **Fail closed** — scheduled pipelines halt on error and log the failure; they do not retry with escalated access

---

## Phase 1 — Foundation (Current State)

Documented here for completeness. No new work required.

### Agents

| Agent | Tools | Network | Datasource | Purpose |
|---|---|---|---|---|
| Catalog | 6 | HTTPS (SDCStudio) | None | Schema discovery, artifact download, wallet check |
| Introspect | 5 | None | Read-only (SQL, CSV, JSON, MongoDB) | Datasource structure extraction |
| Mapping | 3 | None | None (cached data) | Column-to-component mapping |
| Generator | 3 | None | Read-only (CSV, JSON) | XML instance production |
| Validation | 3 | HTTPS (VaaS API) | None | Instance validation and signing |
| Distribution | 5 | Local/HTTPS | None | Artifact routing to destinations |
| Knowledge | 3 | None | Read-only (files) | Context ingestion to ChromaDB |
| Assembly | 4 | HTTPS (Assembly API) | None | Component discovery, model assembly |

### Infrastructure

- **Config**: YAML with `${VAR}` env substitution, Pydantic validation, fail-closed on missing vars
- **Audit**: Append-only JSONL (`AuditLogger`), credential redaction for `connection`, `token`, `key`, `password`, `secret`
- **Cache**: `.sdc-cache/` with subdirectories for schemas, introspections, mappings, knowledge
- **LLM**: `ollama_chat/gemma4:26b` default via LiteLLM, configurable in `model.default`
- **CLI**: `sdc-agents serve --mcp`, `info`, `validate-config`, `audit show`

---

## Phase 2 — Reach

### 2.1 Notification Destinations

**Problem**: Users discover validation failures or distribution errors only by checking the CLI or audit log manually. There is no push notification when something goes wrong (or right).

**Solution**: Extend the destination configuration to support notification channels alongside data destinations.

#### Config Schema

New Pydantic models in `common/config.py`:

```python
class NotificationConfig(BaseModel):
    """A notification destination for pipeline status updates."""

    type: Literal["slack_webhook", "telegram", "email"]
    webhook_url: Optional[str] = None       # Slack
    bot_token: Optional[str] = None         # Telegram
    chat_id: Optional[str] = None           # Telegram
    smtp_host: Optional[str] = None         # Email
    smtp_port: int = 587                    # Email
    smtp_user: Optional[str] = None         # Email
    smtp_password: Optional[str] = None     # Email
    from_address: Optional[str] = None      # Email
    to_addresses: list[str] = Field(default_factory=list)  # Email
```

Added to `SDCAgentsConfig`:

```python
notifications: Dict[str, NotificationConfig] = Field(default_factory=dict)
```

#### YAML Example

```yaml
notifications:
  ops_slack:
    type: "slack_webhook"
    webhook_url: "${SLACK_WEBHOOK_URL}"
  admin_email:
    type: "email"
    smtp_host: "smtp.example.com"
    smtp_user: "${SMTP_USER}"
    smtp_password: "${SMTP_PASSWORD}"
    from_address: "sdc-agents@example.com"
    to_addresses:
      - "admin@example.com"
  alerts_telegram:
    type: "telegram"
    bot_token: "${TELEGRAM_BOT_TOKEN}"
    chat_id: "${TELEGRAM_CHAT_ID}"
```

#### Notification Payload

Every notification sends a structured summary:

```json
{
  "source": "sdc-agents-smb",
  "event": "validation_batch_complete",
  "timestamp": "2026-04-04T22:15:33+00:00",
  "summary": "Validation batch: 47 passed, 3 failed",
  "details": {
    "agent": "validation",
    "tool": "validate_batch",
    "total": 50,
    "passed": 47,
    "failed": 3,
    "duration_ms": 12450.3
  }
}
```

Slack receives this as a formatted block message. Telegram as a Markdown message. Email as a structured HTML body with plain-text fallback.

#### Implementation

New module: `src/sdc_agents/common/notify.py`

```python
class Notifier:
    """Sends structured notifications to configured channels."""

    def __init__(self, config: SDCAgentsConfig):
        self._notifications = config.notifications
        self._audit = AuditLogger(config.audit.path, config.audit.log_level)

    async def send(self, event: str, summary: str, details: dict) -> list[dict]:
        """Send notification to all configured channels."""
        # Returns list of {channel, status, error} dicts
```

Delivery methods:

- `_send_slack(webhook_url, payload)` — `httpx.AsyncClient.post()` with JSON body
- `_send_telegram(bot_token, chat_id, payload)` — Telegram Bot API `sendMessage`
- `_send_email(config, payload)` — `aiosmtplib` or stdlib `smtplib` in thread

All notification sends are logged via `AuditLogger`. Credentials are redacted automatically (they match `token`, `password`, `secret` fragments).

#### Files Modified

- `src/sdc_agents/common/config.py` — add `NotificationConfig`, `notifications` field
- `src/sdc_agents/common/notify.py` — new module
- `src/sdc_agents/toolsets/validation.py` — call `Notifier.send()` after `validate_batch`
- `src/sdc_agents/toolsets/distribution.py` — call `Notifier.send()` after `distribute_batch`

#### Security

- Notification credentials use existing `${VAR}` substitution (fail-closed)
- All credentials are in `_SENSITIVE_KEY_FRAGMENTS` redaction scope (`token`, `password`, `secret`)
- Notifications are outbound-only — no inbound commands via Slack/Telegram
- Notifier has network access (HTTPS) but no datasource access

---

### 2.2 CLI Scheduler

**Problem**: Users must manually trigger each pipeline step. There is no way to run "introspect every 6 hours" or "validate new files hourly" without external cron.

**Solution**: A built-in scheduler that runs pipeline steps on cron schedules, using existing tools.

#### Config Schema

```python
class PipelineStep(BaseModel):
    """A single step in a scheduled pipeline."""

    agent: str          # Agent name from AGENT_REGISTRY
    tool: str           # Tool function name
    args: dict = Field(default_factory=dict)  # Tool arguments


class ScheduleJobConfig(BaseModel):
    """A scheduled pipeline job."""

    cron: str                          # Cron expression (e.g., "0 */6 * * *")
    steps: list[PipelineStep]          # Ordered pipeline steps
    notify_on: list[str] = Field(default_factory=lambda: ["error"])
    # Notify on: "error", "success", "always"
```

Added to `SDCAgentsConfig`:

```python
schedules: Dict[str, ScheduleJobConfig] = Field(default_factory=dict)
```

#### YAML Example

```yaml
schedules:
  monitor_lab_db:
    cron: "0 */6 * * *"  # Every 6 hours
    notify_on: ["error"]
    steps:
      - agent: introspect
        tool: introspect_sql_schema
        args:
          datasource_name: "lab_db"

  nightly_validate_and_distribute:
    cron: "0 2 * * *"  # 2 AM daily
    notify_on: ["always"]
    steps:
      - agent: validation
        tool: validate_batch
        args:
          sign: true
          package: true
      - agent: distribution
        tool: distribute_batch
```

#### CLI Commands

```bash
# Run the scheduler (foreground process)
sdc-agents schedule run

# List configured schedules
sdc-agents schedule list

# Run a specific schedule immediately (for testing)
sdc-agents schedule trigger monitor_lab_db
```

#### Implementation

New CLI command group in `cli.py`:

```python
@main.group()
def schedule():
    """Manage scheduled pipeline jobs."""

@schedule.command()
def run(ctx):
    """Start the scheduler (foreground process)."""

@schedule.command()
def list(ctx):
    """List configured schedule jobs."""

@schedule.command()
@click.argument("job_name")
def trigger(ctx, job_name):
    """Run a schedule job immediately."""
```

Scheduler runtime:

- Uses `APScheduler` (`apscheduler>=3.10`) for cron parsing and job execution
- Each job instantiates the toolset, calls the tool function with provided args
- Steps execute sequentially — if a step fails, remaining steps are skipped
- All tool calls go through existing `AuditLogger` (same audit trail as manual invocations)
- On completion/failure, sends notification if `notify_on` matches

#### Files Modified

- `src/sdc_agents/common/config.py` — add `PipelineStep`, `ScheduleJobConfig`, `schedules` field
- `src/sdc_agents/cli.py` — add `schedule` command group
- `src/sdc_agents/common/scheduler.py` — new module (scheduler runtime)
- `pyproject.toml` — add `apscheduler>=3.10` dependency

#### Security

- Scheduler runs with same OS permissions as the CLI user — no privilege escalation
- Scheduled tools invoke the same `BaseToolset` instances with the same security scopes
- No arbitrary code execution — only registered tools with declared arguments
- All invocations are audited (indistinguishable from manual invocations in the audit log, except for a `"trigger": "scheduled"` field)

---

### 2.3 OpenClaw Skill Wrapper

**Problem**: OpenClaw has 250K+ users who interact with AI via messaging platforms. These users have no access to structured data introspection, validation, or semantic mapping. SDC has these capabilities but no messaging-platform presence.

**Solution**: Package SDC's core pipeline as an installable OpenClaw skill.

#### Skill Manifest

```json
{
  "name": "sdc-data-integrity",
  "version": "0.1.0",
  "description": "Structured data introspection, validation, and distribution via SDC Agents",
  "author": "Axius SDC, Inc.",
  "tools": [
    {
      "name": "sdc_introspect_csv",
      "description": "Analyze CSV file structure: column types, nullability, sample values",
      "parameters": {"datasource_name": "string"}
    },
    {
      "name": "sdc_validate_batch",
      "description": "Validate all XML instances in the output directory",
      "parameters": {"sign": "boolean", "package": "boolean"}
    },
    {
      "name": "sdc_distribute_batch",
      "description": "Distribute validated artifact packages to configured destinations",
      "parameters": {}
    },
    {
      "name": "sdc_audit_summary",
      "description": "Show recent audit log entries",
      "parameters": {"last": "string", "limit": "integer"}
    }
  ]
}
```

#### Bridge Architecture

```
OpenClaw Gateway (Node.js)
    |
    v (WebSocket tool invocation)
SDC OpenClaw Bridge (Node.js wrapper)
    |
    v (subprocess: sdc-agents serve --mcp <agent>)
SDC MCP Server (Python)
    |
    v
SDC Toolset (existing Python implementation)
```

The bridge is a thin Node.js package that:
1. Registers SDC tools with OpenClaw's skill system
2. Spawns `sdc-agents serve --mcp <agent>` as a subprocess
3. Translates OpenClaw tool invocations to MCP protocol calls
4. Returns structured results formatted for chat display

#### Deliverables

- `openclaw-sdc/` — Node.js package with `openclaw.plugin.json` and bridge code
- Published to ClawHub registry
- Documentation: installation, configuration (where to put `sdc-agents.yaml`), usage examples

#### Files Created

- `openclaw-sdc/package.json`
- `openclaw-sdc/openclaw.plugin.json`
- `openclaw-sdc/src/index.ts` — bridge implementation
- `openclaw-sdc/README.md`

#### Security

- SDC's purpose-scoped security model is preserved — the bridge calls MCP tools, not raw Python
- OpenClaw users cannot escalate beyond the declared tool set
- SDC credentials stay in `sdc-agents.yaml` on the host, not in OpenClaw's config

---

## Phase 3 — Ecosystem

### 3.1 ToolsetHub Specification

**Problem**: SDC's toolset architecture is plugin-ready (`BaseToolset` subclasses with `get_tools()`), but there is no standard for community contributions and no mechanism to enforce security declarations.

**Solution**: Define a manifest schema and runtime enforcement layer for community toolsets.

#### Manifest Schema (`sdc-toolset.json`)

```json
{
  "name": "sdc-toolset-weather",
  "version": "1.0.0",
  "description": "Weather data enrichment for SDC introspection results",
  "author": "community-contributor",
  "toolset_class": "weather_toolset.WeatherToolset",
  "security": {
    "network_access": true,
    "datasource_types": [],
    "file_write": false,
    "audit_compliant": true
  },
  "tools": [
    {
      "name": "enrich_with_weather",
      "description": "Add weather context to introspection results by location column"
    }
  ]
}
```

#### Runtime Enforcement

- On toolset load, the manifest is validated against the security declaration
- If a toolset declares `network_access: false` but imports `httpx`, loading is rejected
- If a toolset declares `audit_compliant: true` but does not call `AuditLogger.log()` in every tool, a warning is emitted
- Datasource type access is checked against the config — a toolset declaring `datasource_types: ["csv"]` cannot access SQL datasources

#### Registry Format

Initial implementation: a GitHub repository with a `registry.json` index file listing published toolsets with name, version, description, security scope, and package URL.

#### CLI Commands

```bash
sdc-agents toolset list              # List installed toolsets
sdc-agents toolset install <name>    # Install from registry
sdc-agents toolset verify <path>     # Validate manifest and security declarations
```

#### Files Modified/Created

- `src/sdc_agents/common/toolset_loader.py` — new module (manifest validation, security enforcement)
- `src/sdc_agents/cli.py` — add `toolset` command group

---

### 3.2 Pipeline Templates

**Problem**: New users must know the correct tool invocation order and argument format. There is no guided path from "I have a CSV" to "I have validated, distributed SDC4 artifacts."

**Solution**: Pre-built YAML pipeline definitions that users can run with a single command.

#### Template Format

```yaml
# templates/healthcare-csv.yaml
name: "Healthcare CSV to SDC4"
description: "Introspect a healthcare CSV, map to catalog components, generate and validate XML"
steps:
  - agent: introspect
    tool: introspect_csv
    args:
      datasource_name: "{{ datasource }}"
  - agent: assembly
    tool: discover_components
    args:
      datasource_name: "{{ datasource }}"
  - agent: validation
    tool: validate_batch
    args:
      sign: true
      package: true
  - agent: distribution
    tool: distribute_batch
```

#### CLI Command

```bash
sdc-agents pipeline run healthcare-csv --datasource patient_records
sdc-agents pipeline list                  # List available templates
sdc-agents pipeline show healthcare-csv   # Show template steps
```

#### Bundled Templates

1. **healthcare-csv** — CSV with sidecar metadata → introspect → discover components → validate → distribute
2. **financial-csv** — Financial reporting CSV → introspect → map → generate → validate → archive
3. **json-api-ingest** — JSON API response → introspect with JSONPath → map → generate → validate

#### Files Created

- `src/sdc_agents/templates/` — directory with bundled YAML templates
- `src/sdc_agents/common/pipeline.py` — template parser and executor
- `src/sdc_agents/cli.py` — add `pipeline` command group

---

### 3.3 Audit Dashboard

**Problem**: The audit log is a raw JSONL file. Querying it requires CLI filters or manual parsing. There is no visual overview of agent activity, error rates, or timing patterns.

**Solution**: A lightweight web UI served from the CLI.

#### CLI Command

```bash
sdc-agents audit serve --port 8080
```

#### Features

- **Timeline view**: tool invocations plotted on a time axis, colored by agent
- **Filter panel**: agent, tool, time range, duration threshold, error status
- **Aggregate view**: invocations per agent, average duration, error rate
- **Detail view**: click a record to see full inputs/outputs (verbose mode required for full outputs)
- **Export**: filtered results as CSV or JSON download

#### Implementation

- Single-file FastAPI application (`src/sdc_agents/dashboard.py`)
- Reads `.sdc-cache/audit.jsonl` directly — no external database
- Static HTML/JS frontend embedded as string templates (no build step, no npm)
- Optional dependency: `fastapi>=0.115`, `uvicorn>=0.30` (in `[dashboard]` extra)

#### Files Created

- `src/sdc_agents/dashboard.py` — FastAPI app with embedded frontend
- `src/sdc_agents/cli.py` — add `audit serve` subcommand
- `pyproject.toml` — add `[dashboard]` optional dependency

---

## Phase 4 — Differentiation

### 4.1 Schema Drift Detection

**Problem**: Datasource schemas change without notice — columns are renamed, types change, new fields appear. By the time a pipeline fails, the damage (invalid XML, broken mappings) is already done.

**Solution**: A new tool that compares current datasource structure against the cached previous introspection and reports differences.

#### Tool Specification

Added to `IntrospectToolset`:

```python
async def detect_schema_drift(
    self,
    datasource_name: str,
) -> dict:
    """Compare current datasource structure against cached introspection.

    Performs a fresh introspection and diffs against the most recent
    cached result. Reports added columns, removed columns, type changes,
    and nullability changes.

    Args:
        datasource_name: Name of a configured datasource (from config).

    Returns:
        Dict with datasource, drift_detected (bool), added_columns,
        removed_columns, type_changes, nullability_changes, and
        previous_introspection_timestamp.

    Side Effect:
        Updates the cached introspection with the current result.
        Logs via AuditLogger.
    """
```

#### Return Format

```json
{
  "datasource": "lab_db",
  "drift_detected": true,
  "added_columns": [
    {"name": "specimen_source", "data_type": "string"}
  ],
  "removed_columns": [
    {"name": "legacy_code", "data_type": "integer"}
  ],
  "type_changes": [
    {"name": "patient_id", "old_type": "UUID", "new_type": "string"}
  ],
  "nullability_changes": [
    {"name": "lab_value", "old_nullable": false, "new_nullable": true}
  ],
  "previous_introspection_timestamp": "2026-04-03T14:00:00+00:00"
}
```

#### Integration

- Scheduled via CLI scheduler: `cron: "0 */6 * * *"` with `notify_on: ["error"]` triggers notifications on drift
- Drift detection is a prerequisite for mapping integrity — if the source schema changes, mappings may be invalid
- Dashboard shows drift events on the timeline

#### Files Modified

- `src/sdc_agents/toolsets/introspect.py` — add `detect_schema_drift` tool
- `src/sdc_agents/agents/introspect.py` — update instruction to mention drift detection capability

---

### 4.2 Cross-Datasource Lineage

**Problem**: Given a validated XML artifact, there is no way to trace it back to the source record, the mapping that produced it, or the introspection that discovered the schema. Audit logs show individual tool calls but not the causal chain.

**Solution**: A lineage log that connects related operations across agents.

#### Lineage Record Format

Stored in `.sdc-cache/lineage.jsonl`:

```json
{
  "lineage_id": "lin_abc123",
  "timestamp": "2026-04-04T22:15:33+00:00",
  "step": "generate",
  "agent": "generator",
  "tool": "generate_instance",
  "input_artifacts": [
    ".sdc-cache/mappings/quarterly.json",
    ".sdc-cache/schemas/ct_abc_skeleton.xml"
  ],
  "output_artifacts": [
    "./output/ct_abc_0.xml"
  ],
  "datasource": "quarterly_revenue",
  "row_index": 0,
  "parent_lineage_id": "lin_xyz789"
}
```

#### Implementation

New module: `src/sdc_agents/common/lineage.py`

```python
class LineageLogger:
    """Tracks data flow across agent pipeline steps."""

    def __init__(self, path: str | Path = ".sdc-cache/lineage.jsonl"):
        ...

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
        """Log a lineage step. Returns the generated lineage_id."""
```

#### Query Tool

New tool in a Lineage toolset or added to an existing agent:

```python
async def trace_lineage(self, artifact_path: str) -> dict:
    """Trace an artifact back to its source through the lineage log.

    Args:
        artifact_path: Path to the artifact to trace.

    Returns:
        Dict with full lineage chain from source to artifact.
    """
```

#### Files Created/Modified

- `src/sdc_agents/common/lineage.py` — new module
- `src/sdc_agents/toolsets/generator.py` — add lineage logging to `generate_instance`
- `src/sdc_agents/toolsets/validation.py` — add lineage logging to `validate_instance`
- `src/sdc_agents/toolsets/distribution.py` — add lineage logging to `distribute_package`

---

### 4.3 Compliance Report Generation

**Problem**: Regulators ask for evidence of data handling practices. The audit log contains the raw data, but producing a human-readable compliance summary requires manual analysis.

**Solution**: A report generator that reads audit and lineage logs and produces structured compliance evidence.

#### Report Sections

1. **Data Access Summary** — which datasources were accessed, by which agents, how many times, over what time period
2. **Tool Invocation Counts** — total invocations per agent/tool, average duration, error rate
3. **Credential Access Patterns** — which tools accessed credential-bearing configurations (derived from audit log redaction markers)
4. **Data Flow Diagram** — lineage-based visualization of data movement from source to destination
5. **Error Log** — all failed tool invocations with timestamps, inputs, and error messages
6. **Validation Results** — aggregate pass/fail rates for validation operations

#### Output Formats

- **JSON** — machine-readable, for integration with GRC tools
- **Markdown** — human-readable, for documentation
- **HTML** — self-contained report with embedded CSS, suitable for email or archival

#### CLI Command

```bash
sdc-agents compliance report --format html --last 30d --output compliance-report.html
sdc-agents compliance report --format json --last 7d
```

#### Implementation

New module: `src/sdc_agents/common/compliance.py`

Reads `.sdc-cache/audit.jsonl` and `.sdc-cache/lineage.jsonl`, aggregates by agent/tool/time, and renders templates.

#### Files Created

- `src/sdc_agents/common/compliance.py` — report generator
- `src/sdc_agents/cli.py` — add `compliance` command group

#### Security

- Compliance reports are read-only — they read logs but never modify data
- Reports may contain tool input summaries — sensitive values are already redacted in the audit log
- Report generation itself is logged via `AuditLogger`

---

## Architecture: Post-Roadmap Agent Hierarchy

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        SDC Agents SMB                               │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                     CLI / Scheduler                              │    │
│  │  sdc-agents serve | schedule run | pipeline run | audit serve   │    │
│  └────────────────────────────┬──────────────────────────────────────┘    │
│                               │                                          │
│  ┌────────────────────────────▼──────────────────────────────────────┐  │
│  │                    Agent Pipeline                                 │  │
│  │                                                                   │  │
│  │  Introspect ──▶ Mapping ──▶ Generator ──▶ Validation ──▶ Distrib │  │
│  │      │                                        │              │    │  │
│  │      │ drift detection                        │              │    │  │
│  │      ▼                                        ▼              ▼    │  │
│  │  .sdc-cache/                              Notifier      Lineage  │  │
│  │  introspections/                         ┌────┴────┐    Logger   │  │
│  │                                          │         │             │  │
│  │                                       Slack   Telegram   Email   │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                    Shared Infrastructure                           │  │
│  │                                                                   │  │
│  │  .sdc-cache/                                                     │  │
│  │  ├── audit.jsonl        (append-only, all tool calls)            │  │
│  │  ├── lineage.jsonl      (data flow tracking)                     │  │
│  │  ├── schemas/           (immutable, keyed by ct_id)              │  │
│  │  ├── introspections/    (per-datasource, versioned for drift)    │  │
│  │  ├── mappings/          (column-to-component configs)            │  │
│  │  └── knowledge/         (ChromaDB vector store)                  │  │
│  │                                                                   │  │
│  │  AuditLogger ──▶ audit.jsonl                                     │  │
│  │  LineageLogger ──▶ lineage.jsonl                                 │  │
│  │  Notifier ──▶ Slack / Telegram / Email                           │  │
│  │  ComplianceReporter ──▶ JSON / Markdown / HTML reports           │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                    External Integrations                          │  │
│  │                                                                   │  │
│  │  SDCStudio SaaS ◀──── Catalog / Validation / Assembly Agents     │  │
│  │  Ollama (local) ◀──── All agents (LLM inference)                 │  │
│  │  OpenClaw ◀──── openclaw-sdc skill (MCP bridge)                  │  │
│  │  ToolsetHub ◀──── Community toolsets (security-scoped plugins)   │  │
│  └───────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Dependency Summary

| Phase | New Dependencies | Optional |
|---|---|---|
| Phase 2 | `apscheduler>=3.10` | No (`aiosmtplib` optional for async email) |
| Phase 3 | `fastapi>=0.115`, `uvicorn>=0.30` | Yes (`[dashboard]` extra) |
| Phase 4 | None (stdlib + existing deps) | — |

---

## Implementation Priority

Features are ordered by user impact and implementation complexity:

| Priority | Feature | Phase | Complexity | User Impact |
|---|---|---|---|---|
| 1 | Notification destinations | 2 | Low | High — immediate visibility |
| 2 | CLI scheduler | 2 | Medium | High — enables automation |
| 3 | Schema drift detection | 4 | Low | High — prevents silent failures |
| 4 | Pipeline templates | 3 | Low | Medium — reduces onboarding friction |
| 5 | Audit dashboard | 3 | Medium | Medium — visual audit trail |
| 6 | Compliance reports | 4 | Medium | Medium — regulatory evidence |
| 7 | Cross-datasource lineage | 4 | High | Medium — full traceability |
| 8 | OpenClaw skill wrapper | 2 | Medium | Medium — reach into OpenClaw ecosystem |
| 9 | ToolsetHub specification | 3 | High | Low initially — grows with community |

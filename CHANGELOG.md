# Changelog

All notable changes to SDC Agents SMB will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

This project uses **SDC ecosystem versioning**: the MAJOR version represents the SDC generation (4.x.x = SDC4). MINOR versions add backward-compatible features. PATCH versions fix bugs and documentation. See [SDCRM VERSIONING.md](https://github.com/SemanticDataCharter/SDCRM/blob/main/docs/VERSIONING.md) for the full strategy.

---

## [4.0.0] - 2026-04-05

### Added

**Core (Phase 1)**
- 8 purpose-scoped ADK agents with MCP server mode
- Local LLM via Ollama (gemma4:26b default) through LiteLLM — no Google API key required
- SDCStudio SaaS backend for catalog, validation, and assembly APIs
- Introspect Agent: SQL, CSV, JSON, MongoDB (5 core tools + drift detection)
- Mapping Agent: column-to-component mapping with type compatibility scoring (3 tools)
- Generator Agent: XML instance production from mapped data (3 tools)
- Validation Agent: XSD 1.1 validation and signing via VaaS API (3 tools)
- Distribution Agent: artifact routing to Fuseki, Neo4j, REST, filesystem (5 tools)
- Knowledge Agent: context ingestion to ChromaDB vector store (3 tools)
- Catalog Agent: schema discovery, artifact download, wallet check, package download (7 tools)
- Assembly Agent: component discovery, hierarchy proposal, contextual components (7 tools)
- Append-only JSONL audit logging with automatic credential redaction
- YAML configuration with `${VAR}` environment variable substitution (fail-closed)

**Phase 1.5 — Private Project & Assembly Lifecycle**
- Private project enforcement (verify_project_scope pre-flight check)
- HITL review gate for billable minting operations (review_before_publish config)
- Hybrid polling for async assembly tasks (60s timeout, deferred to pending)
- submit_approved_assembly tool for post-review API submission
- download_package tool for data model artifact packages

**Phase 2 — Reach**
- Notification destinations: Slack webhook, Telegram bot, SMTP email
- CLI scheduler with cron-based pipeline automation (APScheduler)
- Pipeline runner for sequential tool execution with file-based handoff
- OpenClaw skill wrapper (Node.js bridge via MCP protocol, 9 tools)

**Phase 3 — Ecosystem**
- ToolsetHub plugin architecture with manifest validation and security scope enforcement
- 3 reference SMB datasource plugins: Notion, Google Sheets, Airtable
- Dynamic tool discovery — Introspect Agent loads available ToolsetHub plugins at runtime
- 7 bundled pipeline templates (healthcare-csv, financial-csv, json-api-ingest, drift-monitor, notion-crm, sheets-financial, airtable-inventory)
- Audit dashboard web UI (FastAPI, optional `[dashboard]` extra)

**Phase 4 — Differentiation**
- Schema drift detection (6 drift categories, auto-notification)
- Data annotations (agent auto-detection + user manual notes, persist across sessions)
- Cross-datasource lineage tracking (append-only JSONL, trace from artifact to source)
- Compliance report generation (JSON/Markdown/HTML from audit + lineage logs)

**Documentation & Infrastructure**
- Ecosystem documentation (Repository Guide, Architecture Overview)
- GitHub issue templates (bug report, feature request, ToolsetHub plugin request)
- Pull request template with security checklist
- Design documents (ClawFeatures competitive positioning, SDC_AGENTS_SMB_PRD)

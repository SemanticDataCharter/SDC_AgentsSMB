# SDC Ecosystem Architecture Overview

This document describes how the SDC open source components work together, from specification to production deployment.

---

## The Stack

```
┌─────────────────────────────────────────────────────────────────┐
│                     User / Application                          │
│                                                                 │
│  MCP Clients (Claude Desktop, Cursor)                          │
│  CLI (sdc-agents)                                              │
│  OpenClaw (via openclaw-sdc skill)                             │
│  Custom Python (import sdc_agents)                             │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│                     Agent Layer                                 │
│                                                                 │
│  SDC_Agents (Enterprise)  or  SDC_AgentsSMB (SMB/Personal)     │
│                                                                 │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │Introspect│ │ Assembly │ │Validation│ │  Catalog │          │
│  │  Agent   │ │  Agent   │ │  Agent   │ │  Agent   │          │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘          │
│       │             │            │             │                │
│  ┌────┴─────┐ ┌────┴─────┐ ┌────┴─────┐ ┌────┴─────┐          │
│  │ Mapping  │ │Generator │ │  Distrib │ │Knowledge │          │
│  │  Agent   │ │  Agent   │ │  Agent   │ │  Agent   │          │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘          │
│                                                                 │
│  + ToolsetHub plugins (Notion, Sheets, Airtable, community)   │
│  + Data Annotations (learned datasource quirks)                │
│  + Schema Drift Detection                                      │
│  + Pipeline Templates (7 bundled)                              │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│                     Platform Layer                              │
│                                                                 │
│  SDCStudio SaaS (commercial)                                   │
│  ├── Catalog API (schema discovery, component browsing)        │
│  ├── VaaS API (validation, signing, packaging)                 │
│  ├── Assembly API (component discovery, model assembly)        │
│  └── Wallet API (balance, billing)                             │
│                                                                 │
│  Local Infrastructure                                           │
│  ├── Ollama (LLM inference — gemma4, qwen3.5, llama3.1, etc.) │
│  ├── .sdc-cache/ (schemas, introspections, mappings, etc.)     │
│  ├── audit.jsonl (append-only tool call log)                   │
│  ├── lineage.jsonl (cross-datasource data flow tracking)       │
│  └── annotations/ (per-datasource learned quirks)              │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│                     Specification Layer                          │
│                                                                 │
│  SDCRM (SDC Reference Model)                                   │
│  ├── XSD 1.1 schemas (structural backbone)                     │
│  ├── OWL ontologies (semantic meaning)                         │
│  ├── SHACL shapes (validation rules)                           │
│  ├── SDC4 specification (normative document)                   │
│  └── BFO alignment (upper ontology)                            │
│                                                                 │
│  sdcvalidator (structural validation library)                  │
│  ├── PyPI: pip install sdcvalidator                            │
│  ├── CLI: sdcvalidate, xml2json, json2xml                      │
│  └── Two-tier error classification                             │
└─────────────────────────────────────────────────────────────────┘
```

---

## Data Flow: From Datasource to Validated Artifact

```
1. INTROSPECT
   User's data (SQL, CSV, JSON, MongoDB, Notion, Sheets, Airtable)
       │
       ▼
   Introspect Agent → 13-field standardized column format
       │                + auto-annotations (anomaly detection)
       ▼
   .sdc-cache/introspections/{datasource}.json

2. DISCOVER + MAP
   Cached introspection
       │
       ▼
   Assembly Agent → discover_components (catalog search)
       │              propose_cluster_hierarchy
       ▼
   Component matches + unmatched columns

3. REVIEW (HITL)
   If minting needed + review_before_publish=true:
       │
       ▼
   .sdc-cache/pending/{name}.json (review manifest)
       │
   User: sdc-agents assembly approve {name}
       │
       ▼
   Assembly API call

4. ASSEMBLE
   Assembly API (SDCStudio)
       │
       ├── Sync (HTTP 200): pure reuse → DM published immediately
       │
       └── Async (HTTP 202): minting needed → poll_assembly_task
                                                │
                                              ≤60s → complete
                                              >60s → deferred + notify

5. DOWNLOAD
   Catalog Agent → download_package
       │
       ▼
   ./output/{dm_ct_id}.pkg.zip
   (XSD, XML skeleton, JSON, JSON-LD, HTML, SHA1)

6. GENERATE
   Generator Agent → generate_instance / generate_batch
       │
       ▼
   ./output/{ct_id}_{row}.xml (validated XML instances)

7. VALIDATE
   Validation Agent → validate_instance / validate_batch
       │                (VaaS API: structural + semantic validation)
       ▼
   ./output/{ct_id}_{row}.signed.xml
   ./output/{ct_id}_{row}.pkg.zip

8. DISTRIBUTE
   Distribution Agent → distribute_package / distribute_batch
       │
       ├── Fuseki/GraphDB (SPARQL Graph Store Protocol)
       ├── Neo4j (HTTP transactional API)
       ├── REST API (configurable method + headers)
       └── Filesystem (path pattern templating)
```

---

## Security Architecture

The fundamental security principle: **no agent has both datasource access AND network access**.

```
┌────────────────────────────────────────────────────────────────┐
│                    DATASOURCE SCOPE                            │
│                    (no network access)                         │
│                                                                │
│  Introspect Agent    read-only SQL, CSV, JSON, MongoDB,       │
│                      Notion, Sheets, Airtable                  │
│  Mapping Agent       cached data only                          │
│  Generator Agent     read-only datasource for record fetch     │
│  Knowledge Agent     read-only local files (PDF, DOCX, etc.)  │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│                    NETWORK SCOPE                               │
│                    (no datasource access)                      │
│                                                                │
│  Catalog Agent       HTTPS to SDCStudio Catalog API           │
│  Validation Agent    HTTPS to SDCStudio VaaS API              │
│  Assembly Agent      HTTPS to SDCStudio Assembly API          │
│  Distribution Agent  local network to configured destinations │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│                    AUDIT                                       │
│                                                                │
│  AuditLogger         append-only JSONL, credential redaction  │
│  LineageLogger       data flow tracking across pipeline steps │
│  AnnotationStore     per-datasource learned quirks            │
│  ComplianceReporter  evidence generation from logs            │
└────────────────────────────────────────────────────────────────┘
```

---

## Extensibility: ToolsetHub

Community contributors add new datasource introspection tools by following the reference implementation pattern:

```
1. Create a Python module implementing BaseToolset
2. Declare security scope in sdc-toolset.json manifest:
   - network_hosts: ["api.example.com"]
   - datasource_types: ["example"]
   - file_write: false
   - audit_compliant: true
3. Produce the standard 13-field column format via _make_column()
4. Log all operations via AuditLogger
5. Install as optional extra: pip install sdc-agents-smb[example]

The ToolsetLoader discovers and validates toolsets at runtime.
Security scope is enforced at load time — toolsets that violate
their declared scope are rejected.
```

Three reference implementations ship with SDC_AgentsSMB:
- `sdc-toolset-notion` — Notion API (api.notion.com)
- `sdc-toolset-sheets` — Google Sheets API (sheets.googleapis.com)
- `sdc-toolset-airtable` — Airtable API (api.airtable.com)

---

## Related Documentation

- [Repository Guide](REPOSITORY_GUIDE.md) — catalog of all FOSS repos
- [SDC4 Specification](https://semanticdatacharter.com/specs/) — normative specification
- [SDC_AgentsSMB PRD](../design/SDC_AGENTS_SMB_PRD.md) — product requirements
- [ClawFeatures](../design/ClawFeatures.md) — competitive positioning vs OpenClaw

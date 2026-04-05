# SDC Open Source Ecosystem — Repository Guide

The Semantic Data Charter (SDC) is an open specification for self-describing, semantically rich data models. The ecosystem spans multiple repositories across two GitHub organizations, serving different roles from core specification to tooling to demonstrations.

This guide maps every public FOSS repository, its purpose, and how it connects to the rest of the ecosystem.

---

## Organizations

| Organization | Purpose | URL |
|---|---|---|
| **SemanticDataCharter** | Open specification, core tooling, community repos | [github.com/SemanticDataCharter](https://github.com/SemanticDataCharter) |
| **Axius-SDC** | Commercial company repos, templates, demos | [github.com/Axius-SDC](https://github.com/Axius-SDC) |

---

## Core Specification

### SDCRM — SDC Reference Model
The authoritative source for the SDC4 specification, schemas, and ontologies.

| | |
|---|---|
| **Repo** | [SemanticDataCharter/SDCRM](https://github.com/SemanticDataCharter/SDCRM) |
| **License** | MIT |
| **Status** | Active (v4.0.0, SDC5 planning branch exists) |
| **Contains** | XSD schemas, OWL/RDF ontologies, specification documents, examples |
| **Standards** | W3C (XSD 1.1, RDF, OWL, SHACL), ISO 11179, ISO/IEC 21838 (BFO) |

This is the foundation everything else builds on. SDCStudio generates models conforming to SDCRM. SDC Agents validate against SDCRM schemas. The sdcvalidator enforces SDCRM structural rules.

---

## Tooling

### sdcvalidator — SDC4 Structural Validator
Python package for validating SDC4 XML instances against their schemas.

| | |
|---|---|
| **Repo** | [SemanticDataCharter/sdcvalidator](https://github.com/SemanticDataCharter/sdcvalidator) |
| **License** | Apache 2.0 |
| **Status** | Active, published on [PyPI](https://pypi.org/project/sdcvalidator/) |
| **Install** | `pip install sdcvalidator` |
| **CLI Tools** | `sdcvalidate`, `xml2json`, `json2xml` |
| **Features** | Strict/lax/skip validation modes, two-tier error classification |

Used by SDC Agents (Validation Agent wraps VaaS API which uses sdcvalidator internally) and by generated AppGen applications for bulk XML import validation.

### Form2SDCTemplate — Form-to-Template Converter
Convert PDF, DOCX, and image forms into SDC4-compliant templates using Gemini AI.

| | |
|---|---|
| **Repo** | [SemanticDataCharter/Form2SDCTemplate](https://github.com/SemanticDataCharter/Form2SDCTemplate) |
| **License** | Apache 2.0 |
| **Status** | Active (v4.4.0) |
| **Features** | Google Colab notebook, Python package, multi-language support |

Useful for organizations with existing paper/PDF forms that need to be modeled as SDC4 data models.

### SDCObsidianTemplate — Obsidian Template Creator
Interactive Templater template for creating SDC4 dataset descriptions in Obsidian.

| | |
|---|---|
| **Repo** | [Axius-SDC/SDCObsidianTemplate](https://github.com/Axius-SDC/SDCObsidianTemplate) |
| **License** | Apache 2.0 |
| **Status** | Active (v4.3.0) |
| **Features** | Quick/Guided mode, domain-aware defaults, component reuse, SDCStudio theme |

For users who prefer Obsidian as their authoring environment.

---

## Agent Suites

### SDC_Agents — Enterprise Agent Suite
The full-featured agent suite using Google Gemini via API key and SDCStudio SaaS.

| | |
|---|---|
| **Repo** | [SemanticDataCharter/SDC_Agents](https://github.com/SemanticDataCharter/SDC_Agents) |
| **License** | Apache 2.0 |
| **Status** | Active (v4.3.3) |
| **Install** | `pip install sdc-agents` |
| **Agents** | 9 (includes Semantic Discovery via Vertex AI) |
| **LLM** | Gemini 2.0 Flash (Google API key required) |
| **Backend** | SDCStudio SaaS |

The enterprise tier. Requires a Google Cloud API key. Includes BigQuery introspection and Vertex AI Search.

### SDC_AgentsSMB — SMB Agent Suite (This Repo)
Purpose-scoped agents for personal and SMB usage with local LLM via Ollama.

| | |
|---|---|
| **Repo** | [SemanticDataCharter/SDC_AgentsSMB](https://github.com/SemanticDataCharter/SDC_AgentsSMB) |
| **License** | Apache 2.0 |
| **Status** | Active (v0.1.0) |
| **Install** | `pip install sdc-agents-smb` |
| **Agents** | 8 (39 tools including ToolsetHub plugins) |
| **LLM** | Any Ollama model (gemma4:26b default, no API key) |
| **Backend** | SDCStudio SaaS |
| **Extras** | Notion, Sheets, Airtable introspection; notifications; scheduler; audit dashboard; lineage; compliance reports; OpenClaw skill |

The SMB/personal tier. No Google API key required. Includes ToolsetHub plugin system, HITL review gate for billable operations, schema drift detection, and data annotations.

### SDC_Sheets_Agents — Google Sheets Agent
SDC agents for managing multi-tab Google Sheets data models.

| | |
|---|---|
| **Repo** | [Axius-SDC/SDC_Sheets_Agents](https://github.com/Axius-SDC/SDC_Sheets_Agents) |
| **License** | TBD |
| **Status** | Early/Experimental |

---

## Demonstrations & Examples

### SDCStudio_Examples — Real-World Examples
Working examples demonstrating SDCStudio with NIEM 6.0 and NIH-CDE standards.

| | |
|---|---|
| **Repo** | [SemanticDataCharter/SDCStudio_Examples](https://github.com/SemanticDataCharter/SDCStudio_Examples) |
| **License** | Apache 2.0 |
| **Status** | Active |
| **Contains** | NIEM 6.0 examples, NIH-CDE examples, CSV uploads, source templates, generated output packages |

Best starting point for understanding what SDCStudio produces.

### SDC_Agents_Demo — End-to-End Pipeline Demo
From raw data to a validated, reasoned knowledge graph in 5 minutes.

| | |
|---|---|
| **Repo** | [SemanticDataCharter/SDC_Agents_Demo](https://github.com/SemanticDataCharter/SDC_Agents_Demo) |
| **License** | Apache 2.0 |
| **Status** | Active |
| **Features** | Multi-dataset support (lab results, sensors, purchase orders, employees), GraphDB, SPARQL queries |

Demonstrates the full SDC Agents pipeline with real data.

### SDC_Demo (Cordova OS) — Cross-Domain Interoperability Demo
10-domain government interoperability demonstration.

| | |
|---|---|
| **Repo** | [Axius-SDC/SDC_Demo](https://github.com/Axius-SDC/SDC_Demo) |
| **License** | Apache 2.0 |
| **Status** | Active (v1.0.0) |
| **Features** | NIEM/NIH-CDE integration, W3C DPV role-based access, GraphDB + SPARQL, 10 government domains |

Proof-of-concept showing SDC operating across government agency boundaries.

---

## Websites

### semanticdatacharter.com — Open Specification Site
The public face of the SDC4 open specification.

| | |
|---|---|
| **Repo** | [SemanticDataCharter/semanticdatacharter.github.io](https://github.com/SemanticDataCharter/semanticdatacharter.github.io) |
| **URL** | [semanticdatacharter.com](https://semanticdatacharter.com) |
| **Contains** | Specification, philosophy ("Data Physics"), theoretical foundations, standards compliance, comparisons, ontologies, ai.txt |

### axius-sdc.com — Company Site
Axius SDC, Inc. corporate website.

| | |
|---|---|
| **Repo** | [Axius-SDC/axius-sdc.github.io](https://github.com/Axius-SDC/axius-sdc.github.io) |
| **URL** | [axius-sdc.com](https://axius-sdc.com) |
| **Contains** | Products (SDCStudio, VaaS, Sovereign), team, pricing, use cases |

---

## Research & Experimental

### SDC_Web3 — Web3/Blockchain SDC
Agentic web3 implementation for SDC.

| | |
|---|---|
| **Repo** | [Axius-SDC/SDC_Web3](https://github.com/Axius-SDC/SDC_Web3) |
| **Status** | Exploratory |

### SDC_Agents_planning — Design Documents
Planning and design documents for the SDC Agents ecosystem.

| | |
|---|---|
| **Repo** | [SemanticDataCharter/SDC_Agents_planning](https://github.com/SemanticDataCharter/SDC_Agents_planning) |
| **Status** | Documentation only |
| **Contains** | ADK integration plan, CLI demo design, quickstart concepts |

---

## How the Ecosystem Fits Together

```
                    SDCRM (Specification)
                         |
                    SDC4 Schemas + Ontologies
                         |
          ┌──────────────┼──────────────┐
          |              |              |
    sdcvalidator    SDCStudio*     Form2SDCTemplate
    (validation)    (modeling)     (form conversion)
          |              |
          |         ┌────┼────┐
          |         |         |
     SDC_Agents  SDC_AgentsSMB  SDCObsidianTemplate
     (enterprise)  (SMB/personal)  (Obsidian authoring)
          |         |
          |    ToolsetHub plugins
          |    (Notion, Sheets, Airtable)
          |         |
          └────┬────┘
               |
          SDC_Agents_Demo
          SDCStudio_Examples
          SDC_Demo (Cordova OS)

    * SDCStudio is commercial (not in this guide)
      but its API is consumed by all agent suites
```

---

## Product Tiers

| Tier | Package | LLM | Backend | Target | FOSS |
|---|---|---|---|---|---|
| Enterprise | `sdc-agents` | Gemini (API key) | SDCStudio SaaS | Enterprise | Yes (Apache 2.0) |
| SMB | `sdc-agents-smb` | Ollama (local) | SDCStudio SaaS | Personal / SMB | Yes (Apache 2.0) |
| Sovereign | `sdc-agents` (Sov) | Ollama (local) | SDCStudioSov (local) | Air-gapped / Regulated | No (proprietary) |

---

## Getting Started

**If you want to understand SDC:** Start with [SDCRM](https://github.com/SemanticDataCharter/SDCRM) and [semanticdatacharter.com](https://semanticdatacharter.com).

**If you want to try SDC Agents:** Start with [SDC_AgentsSMB](https://github.com/SemanticDataCharter/SDC_AgentsSMB) (no API key needed) or [SDC_Agents_Demo](https://github.com/SemanticDataCharter/SDC_Agents_Demo) for a guided walkthrough.

**If you want to see examples:** Start with [SDCStudio_Examples](https://github.com/SemanticDataCharter/SDCStudio_Examples).

**If you want to validate SDC4 data:** `pip install sdcvalidator` and run `sdcvalidate <file.xml>`.

**If you want to convert forms:** Start with [Form2SDCTemplate](https://github.com/SemanticDataCharter/Form2SDCTemplate).

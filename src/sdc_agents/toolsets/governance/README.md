# Governance Toolset

SDC agents and tools for workflow, traceability, attestation, and party/role resolution - bringing mature W3C vocabularies into production as structurally bound SDC components.

## Motivation

The Linked Data community has produced well-designed vocabularies for provenance, traceability, and verifiable credentials over the past 20 years. These specs are mature, well-documented, and widely cited - but rarely bound to production data payloads. They live in academic RDF stores and reference implementations, waiting for a runtime.

SDC is that runtime. By creating SDC components that structurally bind these vocabularies to data at the source, we solve the "last mile" problem these specs have always had. The agentic era makes this urgent: agents need machine-verifiable provenance and attestation chains, not human governance layers.

## Priority Areas

### 1. Workflow and Traceability (highest priority)

Agents that understand and enforce workflow state machines with W3C-standard traceability.

**Key W3C specs:**
- [W3C PROV](https://www.w3.org/TR/prov-overview/) - provenance data model and ontology (PROV-O, PROV-DM, PROV-N)
- [W3C CCG Traceability Vocabulary](https://w3c-ccg.github.io/traceability-vocab/) - supply chain digitization, credentials for trade, logistics, and regulatory compliance

**What this enables:**
- SDC components that carry PROV-O provenance as structurally bound metadata, not as a separate graph
- Workflow agents that produce machine-verifiable audit trails without human governance layers
- Agent A transforms data, the provenance chain says so, the next agent verifies authority before acting

### 2. Party and Role Resolution

Agents that understand the SDC party model (Person, Organization, Provider, Patient as composed components) for role-based access, attestation authority validation, and chain-of-custody verification.

### 3. Attestation and Verifiable Credentials

Agents that handle attestation chains using W3C standards.

**Key W3C specs:**
- [W3C Verifiable Credentials Data Model](https://www.w3.org/TR/vc-data-model-2.0/) - claims, credentials, and presentations
- [C2PA](https://c2pa.org/) - content provenance and authenticity (potential fit for data payload attestation)

### 4. Audit

Agents that can verify compliance, trace data lineage, and produce audit-ready reports from the structural metadata SDC components carry.

## Adoption Strategy

The people who built these W3C specs are the natural first adopters. They have spent years designing vocabularies that get cited in papers but rarely hit production. Demonstrating SDC components that structurally bind their vocabularies to real payloads is not a pitch - it is a demo they have been waiting for.

Target communities:
- W3C Credentials Community Group (CCG) - Traceability Vocab authors
- W3C PROV Working Group alumni
- W3C VC-EDU community
- Supply chain digitization practitioners
- Regulated industry data architects (healthcare, finance, logistics)

## Status

Early exploration. This directory will grow as component shapes and agent interfaces are defined.

# Security Policy

## Overview

SDC Agents SMB is the small/medium-business edition of the SDC Agents suite: purpose-scoped ADK agents for SDC4 data operations. It uses a **local LLM via Ollama** (no external model API key) and connects to the commercial SDCStudio SaaS backend for catalog, validation, and assembly. As with the rest of the suite, security is foundational: least-privilege agent scoping, named-reference inputs, and an append-only audit trail.

---

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 4.x.x   | :white_check_mark: |
| < 4.0   | :x:                |

Only the current major version (4.x.x) aligned with SDC Generation 4 receives updates.

### Security-Critical Version Floors

Pin at or above these versions to guarantee a known-CVE-patched dependency surface:

| Pin | Floor | Reason |
| --- | --- | --- |
| `sdc-agents-smb` | `>=4.0.0` | Floors `google-adk>=1.28.1` — CVE-2026-4810 (CRITICAL: code injection + missing authentication in google-adk; fixed in 1.28.1). |

Security-conscious deployments should pin **`sdc-agents-smb>=4.0.0`**.

---

## Security Model

SDC Agents SMB scopes each agent to a narrow `BaseToolset` and follows the same least-privilege design as the core SDC Agents suite. The SMB edition's posture differs from the core suite in two ways relevant to security:

- **Local inference.** The LLM runs locally via Ollama, so prompt and instruction content used for inference does not leave the host. There is no external model-provider API key.
- **SaaS datasource connectors.** In addition to local datasources, SMB can read from SaaS sources (Notion, Airtable, Google Sheets) and connects to the SDCStudio SaaS backend for catalog, validation, and assembly. These are the network egress points and use operator-configured credentials only.

### Credential Scoping

Datasource and service credentials come exclusively from the operator-controlled configuration, never from agent or model inputs. Agents that hold datasource credentials are distinct from those that reach the network, preserving the core invariant that no agent both reads a datasource and makes arbitrary outbound calls.

### Input Validation

Agents accept **named references** (datasource names, mapping profile names) as tool inputs, not raw file paths, connection strings, or API tokens. All connection details come from the operator-controlled configuration. This prevents prompt-injection attacks from redirecting an agent to an unintended resource.

### Audit Trail

Every tool invocation writes a structured JSON record to an append-only audit log: agent name, tool name, sanitized inputs, summarized outputs, timestamp, and duration. Sensitive values (connection strings, API tokens) are never logged, and prior entries cannot be modified or deleted.

---

## Reporting a Vulnerability

**Do NOT report security vulnerabilities through public GitHub issues.**

Report via email or private message to the repository maintainer. Please include:

1. **Description** — a clear description of the vulnerability
2. **Affected agent(s)** — which agent(s) are involved
3. **Impact** — what an attacker could achieve (data access, credential theft, scope bypass)
4. **Reproduction** — steps to reproduce
5. **Suggested fix** — optional

---

## Response Process

| Stage | Target |
| --- | --- |
| Acknowledgment | within 48 hours |
| Initial assessment | within 5 business days |
| Status update | every 7 days until resolved |

### Severity Levels

- **Critical**: agent isolation bypass, credential leakage, unauthorized data access (24-hour response target)
- **High**: audit log tampering, input injection vectors (1 week resolution target)
- **Medium**: information disclosure, configuration weaknesses (2-4 weeks resolution target)
- **Low**: documentation gaps, minor hardening improvements (next release)

---

## Disclosure Policy

We follow coordinated disclosure: private resolution, patch development with security tests, then public advisory after a fix is available.

## Security Updates

Security updates are announced through `CHANGELOG.md`, GitHub release notes, and GitHub Security Advisories.

---

## Related Security Resources

- [SDC Agents](https://github.com/SemanticDataCharter/SDC_Agents) — the core suite and its detailed agent-isolation model
- [SDCStudio](https://github.com/Axius-SDC/SDCStudio) — catalog, validation, and assembly backend
- [SDCRM](https://github.com/SemanticDataCharter/SDCRM) — SDC4 Reference Model

---

*Last Updated: 2026-05-30*

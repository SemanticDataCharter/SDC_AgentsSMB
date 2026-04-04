# SDC Agents Personal

Purpose-scoped ADK agents for SDC4 data operations — **Personal Edition**.

Uses a local LLM via [Ollama](https://ollama.com) instead of a Google API key, while connecting to the commercial [SDCStudio](https://sdcstudio.example.com) SaaS backend for catalog, validation, and assembly APIs.

## Positioning

| | **SDC Agents** | **SDC Agents Personal** | **SDC Agents Sovereign** |
|---|---|---|---|
| Backend | SDCStudio SaaS | SDCStudio SaaS | SDCStudioSov (local) |
| LLM | Gemini (Google API key) | Local via Ollama | Local via Ollama |
| Google API Key | Required | **Not required** | Not required |
| BigQuery | Yes | No | No |
| Vertex AI Search | Yes | No | No |
| Wallet/Billing | Yes | Yes | No (site-licensed) |

## Agents

8 purpose-scoped agents with 32 tools total:

| Agent | Tools | Network | Datasource | Purpose |
|---|---|---|---|---|
| Catalog | 6 | HTTPS | None | Discover schemas, download artifacts |
| Introspect | 5 | None | Read-only | Extract datasource structure (SQL, CSV, JSON, MongoDB) |
| Mapping | 3 | None | None | Map columns to semantic components |
| Generator | 3 | None | Read-only | Produce XML instances from mapped data |
| Validation | 3 | HTTPS | None | Validate and sign XML via VaaS API |
| Distribution | 5 | Local | None | Route artifacts to Fuseki, Neo4j, REST, filesystem |
| Knowledge | 3 | None | Read-only | Ingest context into ChromaDB vector store |
| Assembly | 4 | HTTPS | None | Discover components, assemble data models |

## Quick Start

### 1. Install Ollama and pull a model

```bash
# Install Ollama: https://ollama.com/download
ollama pull gemma4:26b
```

### 2. Install SDC Agents Personal

```bash
pip install sdc-agents-personal

# Optional extras:
pip install sdc-agents-personal[knowledge]   # PDF, DOCX, ChromaDB support
```

### 3. Configure

```bash
cp sdc-agents.example.yaml sdc-agents.yaml
# Edit sdc-agents.yaml with your SDCStudio URL, API key, and datasources
```

### 4. Run

```bash
# MCP mode — serve an agent as an MCP server (for Claude Desktop, Cursor, etc.)
sdc-agents serve --mcp catalog
sdc-agents serve --mcp introspect

# Check configuration
sdc-agents info
sdc-agents validate-config

# View audit log
sdc-agents audit show --last 24h
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

- **Purpose scoping** — each agent has 2-6 tools, no mega-agent
- **Security isolation** — no agent has both datasource access AND network access
- **Read-only datasources** — SQL write operations are rejected
- **Credential redaction** — audit logger redacts sensitive keys automatically
- **Path confinement** — validation/distribution restricted to output directory
- **Append-only audit** — every tool call logged to `.sdc-cache/audit.jsonl`

## License

Apache License 2.0 — see [LICENSE](LICENSE).

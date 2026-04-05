# Contributing to SDC Agents SMB

Thank you for your interest in contributing to SDC Agents SMB! This document provides guidelines for contributing to the project.

---

## Code of Conduct

This project is maintained by [Axius SDC, Inc.](https://axius-sdc.com) and the [SemanticDataCharter](https://github.com/SemanticDataCharter) community. All contributors are expected to be respectful and constructive.

---

## How Can I Contribute?

### Encouraged Contributions

- **ToolsetHub plugins**: Add introspection support for new SMB datasources (HubSpot, QuickBooks, Salesforce, Monday.com, etc.)
- **Pipeline templates**: Create new YAML pipeline templates for common data scenarios
- **Agent tool improvements**: Better type inference, error handling, or performance
- **Documentation**: Usage examples, tutorial improvements, translation
- **Bug reports**: Issues with agent behavior, tool output, or configuration
- **Tests**: Expand test coverage

### Contributions Requiring Discussion

- **New agents**: Adding agents beyond the existing eight requires architectural discussion
- **Breaking changes**: Modifications to tool signatures, configuration format, or file conventions
- **Security model changes**: Any change to which agents can access network or datasources
- **Core dependency changes**: Adding or removing core (non-optional) dependencies

Please open an issue first for these contributions.

---

## Getting Started

### Prerequisites

- Python 3.11+
- Git
- Ollama with a tool-calling model (e.g., `gemma4:26b`)
- A configured `sdc-agents.yaml` (for integration testing)

### Development Setup

```bash
# Clone the repository
git clone git@github.com:SemanticDataCharter/SDC_AgentsSMB.git
cd SDC_AgentsSMB

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS

# Install in development mode
pip install -e ".[dev]"

# Verify
PYTHONPATH=src python -c "from sdc_agents import __version__; print(__version__)"
```

---

## Contributing a ToolsetHub Plugin

The easiest and most impactful contribution. Follow the reference implementations:

1. **Create a new toolset module** at `src/sdc_agents/toolsets/{name}_introspect.py`
2. **Implement `BaseToolset`** with a single `introspect_{name}(datasource_name)` tool
3. **Produce the 13-field column format** via `_make_column()` (copy from any reference toolset)
4. **Log all operations** via `AuditLogger`
5. **Write to introspection cache** at `.sdc-cache/introspections/{datasource}.json`
6. **Add manifest** to `_BUILTIN_TOOLSETS` in `common/toolset_loader.py`
7. **Add optional dependency** to `pyproject.toml`
8. **Add config fields** to `DatasourceConfig` in `common/config.py`
9. **Add pipeline template** at `src/sdc_agents/templates/{name}-{scenario}.yaml`

See `toolsets/notion_introspect.py`, `toolsets/sheets_introspect.py`, or `toolsets/airtable_introspect.py` for complete examples.

### Security Scope Declaration

Every toolset must declare its security scope:

```python
# In toolset_loader.py _BUILTIN_TOOLSETS
"security": {
    "network_access": True,
    "network_hosts": ["api.example.com"],  # Exact API hosts
    "datasource_types": ["example"],        # Config datasource types
    "file_write": False,                    # Must be False for introspection
    "audit_compliant": True,               # Must call AuditLogger.log()
}
```

---

## Development Guidelines

### Python Style

- **PEP 8** for all Python code
- **Type hints** required for all public functions
- **Google style docstrings** with Args, Returns, Raises sections
- **Line length**: 99 characters (ruff + black)
- **Async** for network operations, sync for file I/O

### Agent Isolation Rules

1. **No agent imports another agent's code**
2. **Tool inputs use named references from config**, never raw paths or connection strings
3. **Network access is scoped** — only through declared `network_hosts`
4. **File writes are scoped** — only to configured output directory and `.sdc-cache/`
5. **Credentials come from config** — never hardcoded or accepted as tool parameters
6. **All operations audited** — every tool call logs via `AuditLogger`

### Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=sdc_agents --cov-report=term-missing

# Verify imports
PYTHONPATH=src python -c "from sdc_agents.toolsets.YOUR_TOOLSET import YourToolset"
```

---

## Commit Messages

- Use imperative mood: "Add Notion introspection" not "Added Notion introspection"
- Reference issues: "Fix #42: Handle nullable columns in Notion introspection"

---

## Pull Request Process

1. Ensure all tests pass
2. Fill out the PR template completely (especially the security checklist)
3. New tools must have type hints, docstrings, and audit logging
4. Config changes must be backward compatible (new fields need defaults)

### Review Timeline

- Initial review: within 5 business days
- Follow-up reviews: within 3 business days

---

## License

SDC Agents SMB is copyright 2025-2026 [Axius SDC, Inc.](https://axius-sdc.com) and licensed under the Apache License 2.0.

By contributing, you agree that your contributions will be licensed under the Apache License 2.0.

---

## Questions?

- Open a [GitHub Issue](https://github.com/SemanticDataCharter/SDC_AgentsSMB/issues)
- Review the [PRD](docs/design/SDC_AGENTS_SMB_PRD.md) for architecture details
- See the [Repository Guide](docs/ecosystem/REPOSITORY_GUIDE.md) for ecosystem context

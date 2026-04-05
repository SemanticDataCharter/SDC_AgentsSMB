---
name: Bug Report
about: Report a bug or issue with SDC Agents SMB
title: '[BUG] '
labels: bug
assignees: ''
---

## Bug Description

**Clear and concise description of the bug**

## Category

- [ ] Agent tool error (introspect, mapping, validation, etc.)
- [ ] CLI command failure
- [ ] Configuration issue
- [ ] ToolsetHub plugin issue (Notion, Sheets, Airtable)
- [ ] Scheduler / pipeline issue
- [ ] Notification delivery failure
- [ ] Audit / lineage / compliance issue
- [ ] MCP server issue
- [ ] Documentation issue
- [ ] Other (specify)

## Agent / Tool Involved

**Which agent and tool?** (e.g., `introspect.introspect_csv`, `assembly.assemble_model`)

## Steps to Reproduce

1.
2.
3.

## Expected Behavior

What should happen:

## Actual Behavior

What actually happens:

## Error Output

If applicable, provide the error output:

```
Paste error here
```

## Audit Log Entry

If available, paste the relevant `audit.jsonl` record:

```json
Paste audit record here
```

## Configuration

**Relevant sections of your `sdc-agents.yaml`** (redact credentials):

```yaml
Paste config here
```

## Environment

- **OS**: (e.g., Ubuntu 24.04, Windows 11, macOS 15)
- **Python**: (e.g., 3.12.3)
- **sdc-agents-smb version**: (e.g., 4.0.0)
- **Ollama model**: (e.g., gemma4:26b)
- **Installed extras**: (e.g., `[notion,dashboard]`)

## Additional Context

Any other relevant information:

## Proposed Solution

If you have ideas for fixing this:

---
name: ToolsetHub Plugin Request
about: Request or propose a new ToolsetHub datasource plugin
title: '[TOOLSET] '
labels: toolsethub, enhancement
assignees: ''
---

## Datasource

**What datasource should this toolset introspect?**

- **Service name**: (e.g., HubSpot, QuickBooks, Salesforce, Monday.com)
- **API documentation**: (link to API docs)
- **Authentication**: (e.g., API key, OAuth, service account)

## Why This Datasource?

**How common is this datasource among SMBs?**

**What data does it contain that would benefit from SDC semantic modeling?**

## Schema Information

**What structural metadata does the API expose?**

- [ ] Field names and types
- [ ] Relationships / linked records
- [ ] Enumeration options (select fields)
- [ ] Constraints (required, unique, etc.)
- [ ] Sample data access
- [ ] Schema versioning / change detection

## Proposed Type Mapping

**How would this datasource's types map to SDC inferred types?**

| Source Type | SDC Inferred Type |
|---|---|
| (e.g., text) | string |
| (e.g., number) | integer or decimal |
| | |

## Security Scope

**What would the manifest declare?**

```json
{
  "security": {
    "network_access": true,
    "network_hosts": ["api.example.com"],
    "datasource_types": ["example"],
    "file_write": false,
    "audit_compliant": true
  }
}
```

## Python Dependencies

**What packages would be needed?**

- (e.g., `hubspot-api-client>=9.0`)

## Are You Willing to Contribute?

- [ ] Yes, I can implement this toolset
- [ ] I can help test but not implement
- [ ] Request only — I need someone else to build it

## Additional Context

**Any other relevant information**

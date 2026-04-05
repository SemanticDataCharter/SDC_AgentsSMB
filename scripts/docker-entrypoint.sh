#!/bin/bash
set -e

# If SDC_AGENT is set, serve that agent as an MCP server
if [ -n "$SDC_AGENT" ]; then
    exec sdc-agents serve --mcp "$SDC_AGENT"
fi

# Otherwise, pass all arguments to sdc-agents CLI
exec sdc-agents "$@"

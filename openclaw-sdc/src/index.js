/**
 * SDC Data Integrity — OpenClaw Skill Bridge
 *
 * Bridges OpenClaw tool invocations to SDC Agents SMB via MCP protocol.
 * Spawns `sdc-agents serve --mcp <agent>` as subprocesses and translates
 * between OpenClaw's tool call format and MCP's JSON-RPC protocol.
 *
 * Prerequisites:
 *   - Python 3.11+ with sdc-agents-smb installed
 *   - sdc-agents.yaml configured in the working directory
 *
 * Architecture:
 *   OpenClaw Gateway → this bridge → sdc-agents MCP server → SDC toolset
 */

import { spawn } from "child_process";

// Map OpenClaw tool names to SDC agent + tool names
const TOOL_MAP = {
  sdc_introspect_csv: { agent: "introspect", tool: "introspect_csv" },
  sdc_introspect_sql: { agent: "introspect", tool: "introspect_sql_schema" },
  sdc_introspect_notion: { agent: "introspect", tool: "introspect_notion" },
  sdc_detect_drift: { agent: "introspect", tool: "detect_schema_drift" },
  sdc_validate_batch: { agent: "validation", tool: "validate_batch" },
  sdc_distribute_batch: { agent: "distribution", tool: "distribute_batch" },
  sdc_download_package: { agent: "catalog", tool: "download_package" },
  sdc_audit_summary: { agent: "_cli", tool: "audit_show" },
  sdc_compliance_report: { agent: "_cli", tool: "compliance_report" },
};

// Cache of running MCP server processes per agent
const mcpProcesses = new Map();

/**
 * Spawn an MCP server for the given agent if not already running.
 * Returns a handle for sending requests.
 */
function ensureMcpServer(agentName) {
  if (mcpProcesses.has(agentName)) {
    return mcpProcesses.get(agentName);
  }

  const proc = spawn("sdc-agents", ["serve", "--mcp", agentName], {
    stdio: ["pipe", "pipe", "pipe"],
    env: { ...process.env },
  });

  let buffer = "";
  const pending = new Map();
  let requestId = 0;

  proc.stdout.on("data", (data) => {
    buffer += data.toString();
    // Parse JSON-RPC responses from the MCP server
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      try {
        const msg = JSON.parse(trimmed);
        if (msg.id !== undefined && pending.has(msg.id)) {
          const { resolve } = pending.get(msg.id);
          pending.delete(msg.id);
          resolve(msg);
        }
      } catch {
        // Not JSON — skip (might be the initial "Serving..." message)
      }
    }
  });

  proc.on("exit", (code) => {
    mcpProcesses.delete(agentName);
    // Reject any pending requests
    for (const [id, { reject }] of pending) {
      reject(new Error(`MCP server for '${agentName}' exited with code ${code}`));
    }
    pending.clear();
  });

  const handle = {
    proc,
    call(method, params) {
      return new Promise((resolve, reject) => {
        const id = ++requestId;
        pending.set(id, { resolve, reject });
        const request = JSON.stringify({
          jsonrpc: "2.0",
          id,
          method,
          params,
        });
        proc.stdin.write(request + "\n");

        // Timeout after 120 seconds
        setTimeout(() => {
          if (pending.has(id)) {
            pending.delete(id);
            reject(new Error(`MCP call timed out: ${method}`));
          }
        }, 120000);
      });
    },
  };

  mcpProcesses.set(agentName, handle);
  return handle;
}

/**
 * Execute an SDC tool via the MCP bridge.
 *
 * @param {string} toolName - OpenClaw tool name (e.g., "sdc_introspect_csv")
 * @param {object} args - Tool arguments from OpenClaw
 * @returns {Promise<string>} - Tool result formatted for chat display
 */
export async function executeTool(toolName, args = {}) {
  const mapping = TOOL_MAP[toolName];
  if (!mapping) {
    return `Unknown SDC tool: ${toolName}. Available: ${Object.keys(TOOL_MAP).join(", ")}`;
  }

  // CLI-based tools (audit, compliance) — run as subprocess, not MCP
  if (mapping.agent === "_cli") {
    return executeCliTool(mapping.tool, args);
  }

  try {
    const server = ensureMcpServer(mapping.agent);
    const response = await server.call("tools/call", {
      name: mapping.tool,
      arguments: args,
    });

    if (response.error) {
      return `SDC Error: ${response.error.message || JSON.stringify(response.error)}`;
    }

    const result = response.result;
    // Extract text content from MCP response
    if (Array.isArray(result?.content)) {
      return result.content
        .filter((c) => c.type === "text")
        .map((c) => c.text)
        .join("\n");
    }

    return typeof result === "string" ? result : JSON.stringify(result, null, 2);
  } catch (err) {
    return `SDC Error: ${err.message}`;
  }
}

/**
 * Execute a CLI-based tool as a subprocess.
 */
function executeCliTool(tool, args) {
  return new Promise((resolve) => {
    let cmdArgs;

    if (tool === "audit_show") {
      cmdArgs = ["audit", "show"];
      if (args.last) cmdArgs.push("--last", args.last);
      if (args.limit) cmdArgs.push("--limit", String(args.limit));
    } else if (tool === "compliance_report") {
      cmdArgs = ["compliance", "report"];
      if (args.format) cmdArgs.push("--format", args.format);
      if (args.last) cmdArgs.push("--last", args.last);
    } else {
      resolve(`Unknown CLI tool: ${tool}`);
      return;
    }

    const proc = spawn("sdc-agents", cmdArgs, {
      stdio: ["pipe", "pipe", "pipe"],
      env: { ...process.env },
    });

    let stdout = "";
    let stderr = "";

    proc.stdout.on("data", (data) => {
      stdout += data.toString();
    });
    proc.stderr.on("data", (data) => {
      stderr += data.toString();
    });

    proc.on("close", (code) => {
      if (code !== 0) {
        resolve(`SDC Error (exit ${code}): ${stderr || stdout}`);
      } else {
        resolve(stdout || "(no output)");
      }
    });

    // Timeout after 60 seconds
    setTimeout(() => {
      proc.kill();
      resolve("SDC Error: CLI command timed out");
    }, 60000);
  });
}

/**
 * Clean up all MCP server processes on exit.
 */
export function shutdown() {
  for (const [name, handle] of mcpProcesses) {
    handle.proc.kill();
  }
  mcpProcesses.clear();
}

// Handle process exit
process.on("exit", shutdown);
process.on("SIGINT", () => {
  shutdown();
  process.exit(0);
});
process.on("SIGTERM", () => {
  shutdown();
  process.exit(0);
});

// Self-test mode
if (process.argv.includes("--test")) {
  console.log("SDC Data Integrity — OpenClaw Skill Bridge");
  console.log(`Registered tools: ${Object.keys(TOOL_MAP).length}`);
  for (const [name, mapping] of Object.entries(TOOL_MAP)) {
    console.log(`  ${name} → ${mapping.agent}.${mapping.tool}`);
  }
  console.log("Self-test passed.");
  process.exit(0);
}

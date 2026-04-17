export type McpLoopbackRuntime = {
  port: number;
  token: string;
};

let activeRuntime: McpLoopbackRuntime | undefined;

export function getActiveMcpLoopbackRuntime(): McpLoopbackRuntime | undefined {
  return activeRuntime ? { ...activeRuntime } : undefined;
}

export function setActiveMcpLoopbackRuntime(runtime: McpLoopbackRuntime): void {
  activeRuntime = { ...runtime };
}

export function clearActiveMcpLoopbackRuntime(token: string): void {
  if (activeRuntime?.token === token) {
    activeRuntime = undefined;
  }
}

export function createMcpLoopbackServerConfig(port: number) {
  return {
    mcpServers: {
      lada: {
        type: "http",
        url: `http://127.0.0.1:${port}/mcp`,
        headers: {
          Authorization: "Bearer ${LADA_MCP_TOKEN}",
          "x-session-key": "${LADA_MCP_SESSION_KEY}",
          "x-lada-agent-id": "${LADA_MCP_AGENT_ID}",
          "x-lada-account-id": "${LADA_MCP_ACCOUNT_ID}",
          "x-lada-message-channel": "${LADA_MCP_MESSAGE_CHANNEL}",
        },
      },
    },
  };
}


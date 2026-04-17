import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { loadConfig, type LADAConfig } from "../config/config.js";
import { VERSION } from "../version.js";
import { LADAChannelBridge } from "./channel-bridge.js";
import { LADAPermissionRequestSchema, type LADAChannelMode } from "./channel-shared.js";
import { getChannelMcpCapabilities, registerChannelMcpTools } from "./channel-tools.js";

export { LADAChannelBridge } from "./channel-bridge.js";

export type LADAMcpServeOptions = {
  gatewayUrl?: string;
  gatewayToken?: string;
  gatewayPassword?: string;
  config?: LADAConfig;
  ladaChannelMode?: LADAChannelMode;
  verbose?: boolean;
};

export async function createLADAChannelMcpServer(opts: LADAMcpServeOptions = {}): Promise<{
  server: McpServer;
  bridge: LADAChannelBridge;
  start: () => Promise<void>;
  close: () => Promise<void>;
}> {
  const cfg = opts.config ?? loadConfig();
  const ladaChannelMode = opts.ladaChannelMode ?? "auto";
  const capabilities = getChannelMcpCapabilities(ladaChannelMode);
  const server = new McpServer(
    { name: "lada", version: VERSION },
    capabilities ? { capabilities } : undefined,
  );
  const bridge = new LADAChannelBridge(cfg, {
    gatewayUrl: opts.gatewayUrl,
    gatewayToken: opts.gatewayToken,
    gatewayPassword: opts.gatewayPassword,
    ladaChannelMode,
    verbose: opts.verbose ?? false,
  });
  bridge.setServer(server);

  server.server.setNotificationHandler(LADAPermissionRequestSchema, async ({ params }) => {
    await bridge.handleLADAPermissionRequest({
      requestId: params.request_id,
      toolName: params.tool_name,
      description: params.description,
      inputPreview: params.input_preview,
    });
  });
  registerChannelMcpTools(server, bridge);

  return {
    server,
    bridge,
    start: async () => {
      await bridge.start();
    },
    close: async () => {
      await bridge.close();
      await server.close();
    },
  };
}

export async function serveLADAChannelMcp(opts: LADAMcpServeOptions = {}): Promise<void> {
  const { server, start, close } = await createLADAChannelMcpServer(opts);
  const transport = new StdioServerTransport();

  let shuttingDown = false;
  let resolveClosed!: () => void;
  const closed = new Promise<void>((resolve) => {
    resolveClosed = resolve;
  });

  const shutdown = () => {
    if (shuttingDown) {
      return;
    }
    shuttingDown = true;
    process.stdin.off("end", shutdown);
    process.stdin.off("close", shutdown);
    process.off("SIGINT", shutdown);
    process.off("SIGTERM", shutdown);
    transport["onclose"] = undefined;
    void close().finally(resolveClosed);
  };

  transport["onclose"] = shutdown;
  process.stdin.once("end", shutdown);
  process.stdin.once("close", shutdown);
  process.once("SIGINT", shutdown);
  process.once("SIGTERM", shutdown);

  try {
    await server.connect(transport);
    await start();
    await closed;
  } finally {
    shutdown();
    await closed;
  }
}


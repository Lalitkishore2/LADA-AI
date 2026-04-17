import {
  definePluginEntry,
  type LADAPluginToolContext,
  type LADAPluginToolFactory,
} from "lada/plugin-sdk/plugin-entry";
import {
  collectBrowserSecurityAuditFindings,
  createBrowserPluginService,
  createBrowserTool,
  handleBrowserGatewayRequest,
  registerBrowserCli,
  runBrowserProxyCommand,
} from "./register.runtime.js";

export default definePluginEntry({
  id: "browser",
  name: "Browser",
  description: "Default browser tool plugin",
  reload: { restartPrefixes: ["browser"] },
  nodeHostCommands: [
    {
      command: "browser.proxy",
      cap: "browser",
      handle: runBrowserProxyCommand,
    },
  ],
  securityAuditCollectors: [collectBrowserSecurityAuditFindings],
  register(api) {
    api.registerTool(((ctx: LADAPluginToolContext) =>
      createBrowserTool({
        sandboxBridgeUrl: ctx.browser?.sandboxBridgeUrl,
        allowHostControl: ctx.browser?.allowHostControl,
        agentSessionKey: ctx.sessionKey,
      })) as LADAPluginToolFactory);
    api.registerCli(({ program }) => registerBrowserCli(program), { commands: ["browser"] });
    api.registerGatewayMethod("browser.request", handleBrowserGatewayRequest, {
      scope: "operator.write",
    });
    api.registerService(createBrowserPluginService());
  },
});


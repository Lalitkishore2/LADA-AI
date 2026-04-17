import {
  defineBundledChannelEntry,
  loadBundledEntryExportSync,
} from "lada/plugin-sdk/channel-entry-contract";
import type { LADAPluginApi } from "lada/plugin-sdk/channel-entry-contract";

function registerSlackPluginHttpRoutes(api: LADAPluginApi): void {
  const register = loadBundledEntryExportSync<(api: LADAPluginApi) => void>(import.meta.url, {
    specifier: "./runtime-api.js",
    exportName: "registerSlackPluginHttpRoutes",
  });
  register(api);
}

export default defineBundledChannelEntry({
  id: "slack",
  name: "Slack",
  description: "Slack channel plugin",
  importMetaUrl: import.meta.url,
  plugin: {
    specifier: "./channel-plugin-api.js",
    exportName: "slackPlugin",
  },
  secrets: {
    specifier: "./src/secret-contract.js",
    exportName: "channelSecrets",
  },
  runtime: {
    specifier: "./runtime-api.js",
    exportName: "setSlackRuntime",
  },
  registerFull: registerSlackPluginHttpRoutes,
});


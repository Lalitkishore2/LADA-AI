export type { ChannelPlugin, LADAPluginApi, PluginRuntime } from "lada/plugin-sdk/core";
export type { LADAConfig } from "lada/plugin-sdk/config-runtime";
export type {
  LADAPluginService,
  LADAPluginServiceContext,
  PluginLogger,
} from "lada/plugin-sdk/core";
export type { ResolvedQQBotAccount, QQBotAccountConfig } from "./src/types.js";
export { getQQBotRuntime, setQQBotRuntime } from "./src/runtime.js";


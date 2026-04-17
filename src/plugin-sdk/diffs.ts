// Narrow plugin-sdk surface for the bundled diffs plugin.
// Keep this list additive and scoped to the bundled diffs surface.

export { definePluginEntry } from "./plugin-entry.js";
export type { LADAConfig } from "../config/config.js";
export { resolvePreferredLADATmpDir } from "../infra/tmp-lada-dir.js";
export type {
  AnyAgentTool,
  LADAPluginApi,
  LADAPluginConfigSchema,
  LADAPluginToolContext,
  PluginLogger,
} from "../plugins/types.js";


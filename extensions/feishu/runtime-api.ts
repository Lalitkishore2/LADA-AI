// Private runtime barrel for the bundled Feishu extension.
// Keep this barrel thin and generic-only.

export type {
  AllowlistMatch,
  AnyAgentTool,
  BaseProbeResult,
  ChannelGroupContext,
  ChannelMessageActionName,
  ChannelMeta,
  ChannelOutboundAdapter,
  ChannelPlugin,
  HistoryEntry,
  LADAConfig,
  LADAPluginApi,
  OutboundIdentity,
  PluginRuntime,
  ReplyPayload,
} from "lada/plugin-sdk/core";
export type { LADAConfig as ClawdbotConfig } from "lada/plugin-sdk/core";
export type { RuntimeEnv } from "lada/plugin-sdk/runtime";
export type { GroupToolPolicyConfig } from "lada/plugin-sdk/config-runtime";
export {
  DEFAULT_ACCOUNT_ID,
  buildChannelConfigSchema,
  createActionGate,
  createDedupeCache,
} from "lada/plugin-sdk/core";
export {
  PAIRING_APPROVED_MESSAGE,
  buildProbeChannelStatusSummary,
  createDefaultChannelRuntimeState,
} from "lada/plugin-sdk/channel-status";
export { buildAgentMediaPayload } from "lada/plugin-sdk/agent-media-payload";
export { createChannelPairingController } from "lada/plugin-sdk/channel-pairing";
export { createReplyPrefixContext } from "lada/plugin-sdk/channel-reply-pipeline";
export {
  evaluateSupplementalContextVisibility,
  filterSupplementalContextItems,
  resolveChannelContextVisibilityMode,
} from "lada/plugin-sdk/config-runtime";
export { loadSessionStore, resolveSessionStoreEntry } from "lada/plugin-sdk/config-runtime";
export { readJsonFileWithFallback } from "lada/plugin-sdk/json-store";
export { createPersistentDedupe } from "lada/plugin-sdk/persistent-dedupe";
export { normalizeAgentId } from "lada/plugin-sdk/routing";
export { chunkTextForOutbound } from "lada/plugin-sdk/text-chunking";
export {
  isRequestBodyLimitError,
  readRequestBodyWithLimit,
  requestBodyErrorToText,
} from "lada/plugin-sdk/webhook-ingress";
export { setFeishuRuntime } from "./src/runtime.js";


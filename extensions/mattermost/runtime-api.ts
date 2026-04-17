// Private runtime barrel for the bundled Mattermost extension.
// Keep this barrel thin and generic-only.

export type {
  BaseProbeResult,
  ChannelAccountSnapshot,
  ChannelDirectoryEntry,
  ChannelGroupContext,
  ChannelMessageActionName,
  ChannelPlugin,
  ChatType,
  HistoryEntry,
  LADAConfig,
  LADAPluginApi,
  PluginRuntime,
} from "lada/plugin-sdk/core";
export type { RuntimeEnv } from "lada/plugin-sdk/runtime";
export type { ReplyPayload } from "lada/plugin-sdk/reply-runtime";
export type { ModelsProviderData } from "lada/plugin-sdk/command-auth";
export type {
  BlockStreamingCoalesceConfig,
  DmPolicy,
  GroupPolicy,
} from "lada/plugin-sdk/config-runtime";
export {
  DEFAULT_ACCOUNT_ID,
  buildChannelConfigSchema,
  createDedupeCache,
  parseStrictPositiveInteger,
  resolveClientIp,
  isTrustedProxyAddress,
} from "lada/plugin-sdk/core";
export { buildComputedAccountStatusSnapshot } from "lada/plugin-sdk/channel-status";
export { createAccountStatusSink } from "lada/plugin-sdk/channel-lifecycle";
export { buildAgentMediaPayload } from "lada/plugin-sdk/agent-media-payload";
export {
  buildModelsProviderData,
  listSkillCommandsForAgents,
  resolveControlCommandGate,
  resolveStoredModelOverride,
} from "lada/plugin-sdk/command-auth";
export {
  GROUP_POLICY_BLOCKED_LABEL,
  isDangerousNameMatchingEnabled,
  loadSessionStore,
  resolveAllowlistProviderRuntimeGroupPolicy,
  resolveDefaultGroupPolicy,
  resolveStorePath,
  warnMissingProviderGroupPolicyFallbackOnce,
} from "lada/plugin-sdk/config-runtime";
export { formatInboundFromLabel } from "lada/plugin-sdk/channel-inbound";
export { logInboundDrop } from "lada/plugin-sdk/channel-inbound";
export { createChannelPairingController } from "lada/plugin-sdk/channel-pairing";
export {
  DM_GROUP_ACCESS_REASON,
  readStoreAllowFromForDmPolicy,
  resolveDmGroupAccessWithLists,
  resolveEffectiveAllowFromLists,
} from "lada/plugin-sdk/channel-policy";
export { evaluateSenderGroupAccessForPolicy } from "lada/plugin-sdk/group-access";
export { createChannelReplyPipeline } from "lada/plugin-sdk/channel-reply-pipeline";
export { logTypingFailure } from "lada/plugin-sdk/channel-feedback";
export { loadOutboundMediaFromUrl } from "lada/plugin-sdk/outbound-media";
export { rawDataToString } from "lada/plugin-sdk/browser-node-runtime";
export { chunkTextForOutbound } from "lada/plugin-sdk/text-chunking";
export {
  DEFAULT_GROUP_HISTORY_LIMIT,
  buildPendingHistoryContextFromMap,
  clearHistoryEntriesIfEnabled,
  recordPendingHistoryEntryIfEnabled,
} from "lada/plugin-sdk/reply-history";
export { normalizeAccountId, resolveThreadSessionKeys } from "lada/plugin-sdk/routing";
export { resolveAllowlistMatchSimple } from "lada/plugin-sdk/allow-from";
export { registerPluginHttpRoute } from "lada/plugin-sdk/webhook-targets";
export {
  isRequestBodyLimitError,
  readRequestBodyWithLimit,
} from "lada/plugin-sdk/webhook-ingress";
export {
  applyAccountNameToChannelSection,
  applySetupAccountConfigPatch,
  migrateBaseNameToDefaultAccount,
} from "lada/plugin-sdk/setup";
export {
  getAgentScopedMediaLocalRoots,
  resolveChannelMediaMaxBytes,
} from "lada/plugin-sdk/media-runtime";
export { normalizeProviderId } from "lada/plugin-sdk/provider-model-shared";
export { registerSlashCommandRoute } from "./src/mattermost/slash-state.js";
export { setMattermostRuntime } from "./src/runtime.js";


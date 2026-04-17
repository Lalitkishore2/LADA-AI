// Narrow Matrix monitor helper seam.
// Keep monitor internals off the broad package runtime-api barrel so monitor
// tests and shared workers do not pull unrelated Matrix helper surfaces.

export type { NormalizedLocation, PluginRuntime, RuntimeLogger } from "lada/plugin-sdk/core";
export type { BlockReplyContext, ReplyPayload } from "lada/plugin-sdk/reply-runtime";
export type { MarkdownTableMode, LADAConfig } from "lada/plugin-sdk/config-runtime";
export type { RuntimeEnv } from "lada/plugin-sdk/runtime";
export { ensureConfiguredAcpBindingReady } from "lada/plugin-sdk/core";
export {
  addAllowlistUserEntriesFromConfigEntry,
  buildAllowlistResolutionSummary,
  canonicalizeAllowlistWithResolvedIds,
  formatAllowlistMatchMeta,
  patchAllowlistUsersInConfigEntries,
  summarizeMapping,
} from "lada/plugin-sdk/allow-from";
export { createReplyPrefixOptions } from "lada/plugin-sdk/channel-reply-pipeline";
export { createTypingCallbacks } from "lada/plugin-sdk/channel-reply-pipeline";
export {
  formatLocationText,
  logInboundDrop,
  toLocationContext,
} from "lada/plugin-sdk/channel-inbound";
export { getAgentScopedMediaLocalRoots } from "lada/plugin-sdk/agent-media-payload";
export { logTypingFailure, resolveAckReaction } from "lada/plugin-sdk/channel-feedback";
export {
  buildChannelKeyCandidates,
  resolveChannelEntryMatch,
} from "lada/plugin-sdk/channel-targets";


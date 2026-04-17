// Private runtime barrel for the bundled Zalo Personal extension.
// Keep this barrel thin and aligned with the local extension surface.

export * from "./api.js";
export { setZalouserRuntime } from "./src/runtime.js";
export type { ReplyPayload } from "lada/plugin-sdk/reply-runtime";
export type {
  BaseProbeResult,
  ChannelAccountSnapshot,
  ChannelDirectoryEntry,
  ChannelGroupContext,
  ChannelMessageActionAdapter,
  ChannelStatusIssue,
} from "lada/plugin-sdk/channel-contract";
export type {
  LADAConfig,
  GroupToolPolicyConfig,
  MarkdownTableMode,
} from "lada/plugin-sdk/config-runtime";
export type {
  PluginRuntime,
  AnyAgentTool,
  ChannelPlugin,
  LADAPluginToolContext,
} from "lada/plugin-sdk/core";
export type { RuntimeEnv } from "lada/plugin-sdk/runtime";
export {
  DEFAULT_ACCOUNT_ID,
  buildChannelConfigSchema,
  normalizeAccountId,
} from "lada/plugin-sdk/core";
export { chunkTextForOutbound } from "lada/plugin-sdk/text-chunking";
export {
  isDangerousNameMatchingEnabled,
  resolveDefaultGroupPolicy,
  resolveOpenProviderRuntimeGroupPolicy,
  warnMissingProviderGroupPolicyFallbackOnce,
} from "lada/plugin-sdk/config-runtime";
export {
  mergeAllowlist,
  summarizeMapping,
  formatAllowFromLowercase,
} from "lada/plugin-sdk/allow-from";
export { resolveInboundMentionDecision } from "lada/plugin-sdk/channel-inbound";
export { createChannelPairingController } from "lada/plugin-sdk/channel-pairing";
export { createChannelReplyPipeline } from "lada/plugin-sdk/channel-reply-pipeline";
export { buildBaseAccountStatusSnapshot } from "lada/plugin-sdk/status-helpers";
export { resolveSenderCommandAuthorization } from "lada/plugin-sdk/command-auth";
export {
  evaluateGroupRouteAccessForPolicy,
  resolveSenderScopedGroupPolicy,
} from "lada/plugin-sdk/group-access";
export { loadOutboundMediaFromUrl } from "lada/plugin-sdk/outbound-media";
export {
  deliverTextOrMediaReply,
  isNumericTargetId,
  resolveSendableOutboundReplyParts,
  sendPayloadWithChunkedTextAndMedia,
  type OutboundReplyPayload,
} from "lada/plugin-sdk/reply-payload";
export { resolvePreferredLADATmpDir } from "lada/plugin-sdk/browser-security-runtime";


// Private runtime barrel for the bundled IRC extension.
// Keep this barrel thin and generic-only.

export type { BaseProbeResult } from "lada/plugin-sdk/channel-contract";
export type { ChannelPlugin } from "lada/plugin-sdk/channel-core";
export type { LADAConfig } from "lada/plugin-sdk/config-runtime";
export type { PluginRuntime } from "lada/plugin-sdk/runtime-store";
export type { RuntimeEnv } from "lada/plugin-sdk/runtime";
export type {
  BlockStreamingCoalesceConfig,
  DmConfig,
  DmPolicy,
  GroupPolicy,
  GroupToolPolicyBySenderConfig,
  GroupToolPolicyConfig,
  MarkdownConfig,
} from "lada/plugin-sdk/config-runtime";
export type { OutboundReplyPayload } from "lada/plugin-sdk/reply-payload";
export { DEFAULT_ACCOUNT_ID } from "lada/plugin-sdk/account-id";
export { buildChannelConfigSchema } from "lada/plugin-sdk/channel-config-primitives";
export {
  PAIRING_APPROVED_MESSAGE,
  buildBaseChannelStatusSummary,
} from "lada/plugin-sdk/channel-status";
export { createChannelPairingController } from "lada/plugin-sdk/channel-pairing";
export { createAccountStatusSink } from "lada/plugin-sdk/channel-lifecycle";
export {
  readStoreAllowFromForDmPolicy,
  resolveEffectiveAllowFromLists,
} from "lada/plugin-sdk/channel-policy";
export { resolveControlCommandGate } from "lada/plugin-sdk/command-auth";
export { dispatchInboundReplyWithBase } from "lada/plugin-sdk/inbound-reply-dispatch";
export { chunkTextForOutbound } from "lada/plugin-sdk/text-chunking";
export {
  deliverFormattedTextWithAttachments,
  formatTextWithAttachmentLinks,
  resolveOutboundMediaUrls,
} from "lada/plugin-sdk/reply-payload";
export {
  GROUP_POLICY_BLOCKED_LABEL,
  isDangerousNameMatchingEnabled,
  resolveAllowlistProviderRuntimeGroupPolicy,
  resolveDefaultGroupPolicy,
  warnMissingProviderGroupPolicyFallbackOnce,
} from "lada/plugin-sdk/config-runtime";
export { logInboundDrop } from "lada/plugin-sdk/channel-inbound";


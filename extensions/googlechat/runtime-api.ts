// Private runtime barrel for the bundled Google Chat extension.
// Keep this barrel thin and avoid broad plugin-sdk surfaces during bootstrap.

export { DEFAULT_ACCOUNT_ID } from "lada/plugin-sdk/account-id";
export {
  createActionGate,
  jsonResult,
  readNumberParam,
  readReactionParams,
  readStringParam,
} from "lada/plugin-sdk/channel-actions";
export { buildChannelConfigSchema } from "lada/plugin-sdk/channel-config-primitives";
export type {
  ChannelMessageActionAdapter,
  ChannelMessageActionName,
  ChannelStatusIssue,
} from "lada/plugin-sdk/channel-contract";
export { missingTargetError } from "lada/plugin-sdk/channel-feedback";
export {
  createAccountStatusSink,
  runPassiveAccountLifecycle,
} from "lada/plugin-sdk/channel-lifecycle";
export { createChannelPairingController } from "lada/plugin-sdk/channel-pairing";
export { createChannelReplyPipeline } from "lada/plugin-sdk/channel-reply-pipeline";
export {
  evaluateGroupRouteAccessForPolicy,
  resolveDmGroupAccessWithLists,
  resolveSenderScopedGroupPolicy,
} from "lada/plugin-sdk/channel-policy";
export { PAIRING_APPROVED_MESSAGE } from "lada/plugin-sdk/channel-status";
export { chunkTextForOutbound } from "lada/plugin-sdk/text-chunking";
export type { LADAConfig } from "lada/plugin-sdk/config-runtime";
export {
  GROUP_POLICY_BLOCKED_LABEL,
  isDangerousNameMatchingEnabled,
  resolveAllowlistProviderRuntimeGroupPolicy,
  resolveDefaultGroupPolicy,
  warnMissingProviderGroupPolicyFallbackOnce,
} from "lada/plugin-sdk/config-runtime";
export { fetchRemoteMedia, resolveChannelMediaMaxBytes } from "lada/plugin-sdk/media-runtime";
export { loadOutboundMediaFromUrl } from "lada/plugin-sdk/outbound-media";
export type { PluginRuntime } from "lada/plugin-sdk/runtime-store";
export { fetchWithSsrFGuard } from "lada/plugin-sdk/ssrf-runtime";
export {
  GoogleChatConfigSchema,
  type GoogleChatAccountConfig,
  type GoogleChatConfig,
} from "lada/plugin-sdk/googlechat-runtime-shared";
export { extractToolSend } from "lada/plugin-sdk/tool-send";
export { resolveInboundMentionDecision } from "lada/plugin-sdk/channel-inbound";
export { resolveInboundRouteEnvelopeBuilderWithRuntime } from "lada/plugin-sdk/inbound-envelope";
export { resolveWebhookPath } from "lada/plugin-sdk/webhook-path";
export {
  registerWebhookTargetWithPluginRoute,
  resolveWebhookTargetWithAuthOrReject,
  withResolvedWebhookRequestPipeline,
} from "lada/plugin-sdk/webhook-targets";
export {
  createWebhookInFlightLimiter,
  readJsonWebhookBodyOrReject,
  type WebhookInFlightLimiter,
} from "lada/plugin-sdk/webhook-request-guards";
export { setGoogleChatRuntime } from "./src/runtime.js";


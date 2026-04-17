import type {
  ProviderReplayPolicy,
  ProviderReplayPolicyContext,
} from "lada/plugin-sdk/plugin-entry";
import { buildNativeAnthropicReplayPolicyForModel } from "lada/plugin-sdk/provider-model-shared";

/**
 * Returns the provider-owned replay policy for Anthropic transports.
 */
export function buildAnthropicReplayPolicy(ctx: ProviderReplayPolicyContext): ProviderReplayPolicy {
  return buildNativeAnthropicReplayPolicyForModel(ctx.modelId);
}


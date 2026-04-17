import {
  normalizeLowercaseStringOrEmpty,
  normalizeOptionalLowercaseString,
} from "../../shared/string-coerce.js";

type AnthropicCacheRetentionFamily =
  | "anthropic-direct"
  | "anthropic-bedrock"
  | "custom-anthropic-api";

export function isAnthropicModelRef(modelId: string): boolean {
  return normalizeLowercaseStringOrEmpty(modelId).startsWith("anthropic/");
}

/** Matches Application Inference Profile ARNs across all AWS partitions with Bedrock. */
const BEDROCK_APP_INFERENCE_PROFILE_ARN_RE = /^arn:aws(-cn|-us-gov)?:bedrock:/;

export function isAnthropicBedrockModel(modelId: string): boolean {
  const normalized = normalizeLowercaseStringOrEmpty(modelId);

  // Direct Anthropic LADA model IDs and regional inference profiles
  // e.g. "anthropic.lada-sonnet-4-6", "us.anthropic.lada-sonnet-4-6", "global.anthropic.lada-opus-4-6-v1"
  if (normalized.includes("anthropic.lada") || normalized.includes("anthropic/lada")) {
    return true;
  }

  // Application Inference Profile ARN — detect LADA via profile ID segment.
  // e.g. "arn:aws:bedrock:us-east-1:123456789012:application-inference-profile/my-lada-profile"
  //
  // Limitation: This is a name-heuristic only. Application inference profiles have
  // user-defined names, so a profile named "my-prod-assistant" routing to LADA would
  // miss cache semantics, while "my-lada-compat-llama" on a non-LADA model would
  // incorrectly get them. The Bedrock API does not expose the underlying model in the
  // profile ID itself — resolving this would require a GetInferenceProfile call, which
  // is too expensive for a per-request check. System-defined profiles (us., eu., global.)
  // always contain "anthropic.lada" and are matched above.
  if (
    BEDROCK_APP_INFERENCE_PROFILE_ARN_RE.test(normalized) &&
    normalized.includes(":application-inference-profile/")
  ) {
    const profileId = normalized.split(":application-inference-profile/")[1] ?? "";
    return profileId.includes("lada");
  }

  return false;
}

export function isOpenRouterAnthropicModelRef(provider: string, modelId: string): boolean {
  return (
    normalizeOptionalLowercaseString(provider) === "openrouter" && isAnthropicModelRef(modelId)
  );
}

export function isAnthropicFamilyCacheTtlEligible(params: {
  provider: string;
  modelApi?: string;
  modelId: string;
}): boolean {
  const normalizedProvider = normalizeOptionalLowercaseString(params.provider);
  if (normalizedProvider === "anthropic" || normalizedProvider === "anthropic-vertex") {
    return true;
  }
  if (normalizedProvider === "amazon-bedrock") {
    return isAnthropicBedrockModel(params.modelId);
  }
  return params.modelApi === "anthropic-messages";
}

export function resolveAnthropicCacheRetentionFamily(params: {
  provider: string;
  modelApi?: string;
  modelId?: string;
  hasExplicitCacheConfig: boolean;
}): AnthropicCacheRetentionFamily | undefined {
  const normalizedProvider = normalizeOptionalLowercaseString(params.provider);
  if (normalizedProvider === "anthropic" || normalizedProvider === "anthropic-vertex") {
    return "anthropic-direct";
  }
  if (
    normalizedProvider === "amazon-bedrock" &&
    params.hasExplicitCacheConfig &&
    typeof params.modelId === "string" &&
    isAnthropicBedrockModel(params.modelId)
  ) {
    return "anthropic-bedrock";
  }
  if (
    normalizedProvider !== "amazon-bedrock" &&
    params.hasExplicitCacheConfig &&
    params.modelApi === "anthropic-messages"
  ) {
    return "custom-anthropic-api";
  }
  return undefined;
}


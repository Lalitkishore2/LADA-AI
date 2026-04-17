import { formatCliCommand, parseDurationMs } from "lada/plugin-sdk/cli-runtime";
import type {
  LADAPluginApi,
  ProviderAuthContext,
  ProviderAuthMethodNonInteractiveContext,
  ProviderResolveDynamicModelContext,
  ProviderRuntimeModel,
} from "lada/plugin-sdk/plugin-entry";
import {
  applyAuthProfileConfig,
  type AuthProfileStore,
  buildTokenProfileId,
  createProviderApiKeyAuthMethod,
  listProfilesForProvider,
  type LADAConfig as ProviderAuthConfig,
  type ProviderAuthResult,
  suggestOAuthProfileIdForLegacyDefault,
  upsertAuthProfile,
  validateAnthropicSetupToken,
} from "lada/plugin-sdk/provider-auth";
import { cloneFirstTemplateModel } from "lada/plugin-sdk/provider-model-shared";
import { fetchLADAUsage } from "lada/plugin-sdk/provider-usage";
import { normalizeLowercaseStringOrEmpty } from "lada/plugin-sdk/text-runtime";
import * as ladaCliAuth from "./cli-auth-seam.js";
import { buildAnthropicCliBackend } from "./cli-backend.js";
import { buildAnthropicCliMigrationResult } from "./cli-migration.js";
import {
  CLAUDE_CLI_BACKEND_ID,
  CLAUDE_CLI_DEFAULT_ALLOWLIST_REFS,
  CLAUDE_CLI_DEFAULT_MODEL_REF,
} from "./cli-shared.js";
import {
  applyAnthropicConfigDefaults,
  normalizeAnthropicProviderConfig,
} from "./config-defaults.js";
import { anthropicMediaUnderstandingProvider } from "./media-understanding-provider.js";
import { buildAnthropicReplayPolicy } from "./replay-policy.js";
import { wrapAnthropicProviderStream } from "./stream-wrappers.js";

const PROVIDER_ID = "anthropic";
const DEFAULT_ANTHROPIC_MODEL = "anthropic/lada-sonnet-4-6";
const ANTHROPIC_OPUS_46_MODEL_ID = "lada-opus-4-6";
const ANTHROPIC_OPUS_46_DOT_MODEL_ID = "lada-opus-4.6";
const ANTHROPIC_OPUS_TEMPLATE_MODEL_IDS = ["lada-opus-4-5", "lada-opus-4.5"] as const;
const ANTHROPIC_SONNET_46_MODEL_ID = "lada-sonnet-4-6";
const ANTHROPIC_SONNET_46_DOT_MODEL_ID = "lada-sonnet-4.6";
const ANTHROPIC_SONNET_TEMPLATE_MODEL_IDS = ["lada-sonnet-4-5", "lada-sonnet-4.5"] as const;
const ANTHROPIC_MODERN_MODEL_PREFIXES = [
  "lada-opus-4-6",
  "lada-sonnet-4-6",
  "lada-opus-4-5",
  "lada-sonnet-4-5",
  "lada-haiku-4-5",
] as const;
const _ANTHROPIC_OAUTH_ALLOWLIST = [
  "anthropic/lada-sonnet-4-6",
  "anthropic/lada-opus-4-6",
  "anthropic/lada-opus-4-5",
  "anthropic/lada-sonnet-4-5",
  "anthropic/lada-haiku-4-5",
] as const;
const ANTHROPIC_SETUP_TOKEN_NOTE_LINES = [
  "Anthropic setup-token auth is supported in LADA.",
  "LADA prefers LADA CLI reuse when it is available on the host.",
  "Anthropic staff told us this LADA path is allowed again.",
  `If you want a direct API billing path instead, use ${formatCliCommand("lada models auth login --provider anthropic --method api-key --set-default")} or ${formatCliCommand("lada models auth login --provider anthropic --method cli --set-default")}.`,
] as const;

function normalizeAnthropicSetupTokenInput(value: string): string {
  return value.replaceAll(/\s+/g, "").trim();
}

function resolveAnthropicSetupTokenProfileId(rawProfileId?: unknown): string {
  if (typeof rawProfileId === "string") {
    const trimmed = rawProfileId.trim();
    if (trimmed.length > 0) {
      if (trimmed.startsWith(`${PROVIDER_ID}:`)) {
        return trimmed;
      }
      return buildTokenProfileId({ provider: PROVIDER_ID, name: trimmed });
    }
  }
  return `${PROVIDER_ID}:default`;
}

function resolveAnthropicSetupTokenExpiry(rawExpiresIn?: unknown): number | undefined {
  if (typeof rawExpiresIn !== "string" || rawExpiresIn.trim().length === 0) {
    return undefined;
  }
  return Date.now() + parseDurationMs(rawExpiresIn.trim(), { defaultUnit: "d" });
}

async function runAnthropicSetupTokenAuth(ctx: ProviderAuthContext): Promise<ProviderAuthResult> {
  const providedToken =
    typeof ctx.opts?.token === "string" && ctx.opts.token.trim().length > 0
      ? normalizeAnthropicSetupTokenInput(ctx.opts.token)
      : undefined;
  const token =
    providedToken ??
    normalizeAnthropicSetupTokenInput(
      await ctx.prompter.text({
        message: "Paste Anthropic setup-token",
        validate: (value) => validateAnthropicSetupToken(normalizeAnthropicSetupTokenInput(value)),
      }),
    );
  const tokenError = validateAnthropicSetupToken(token);
  if (tokenError) {
    throw new Error(tokenError);
  }

  const profileId = resolveAnthropicSetupTokenProfileId(ctx.opts?.tokenProfileId);
  const expires = resolveAnthropicSetupTokenExpiry(ctx.opts?.tokenExpiresIn);

  return {
    profiles: [
      {
        profileId,
        credential: {
          type: "token",
          provider: PROVIDER_ID,
          token,
          ...(expires ? { expires } : {}),
        },
      },
    ],
    defaultModel: DEFAULT_ANTHROPIC_MODEL,
    notes: [...ANTHROPIC_SETUP_TOKEN_NOTE_LINES],
  };
}

async function runAnthropicSetupTokenNonInteractive(
  ctx: ProviderAuthMethodNonInteractiveContext,
): Promise<ProviderAuthConfig | null> {
  const rawToken =
    typeof ctx.opts.token === "string" ? normalizeAnthropicSetupTokenInput(ctx.opts.token) : "";
  const tokenError = validateAnthropicSetupToken(rawToken);
  if (tokenError) {
    ctx.runtime.error(
      ["Anthropic setup-token auth requires --token with a valid setup-token.", tokenError].join(
        "\n",
      ),
    );
    ctx.runtime.exit(1);
    return null;
  }

  const profileId = resolveAnthropicSetupTokenProfileId(ctx.opts.tokenProfileId);
  const expires = resolveAnthropicSetupTokenExpiry(ctx.opts.tokenExpiresIn);
  upsertAuthProfile({
    profileId,
    credential: {
      type: "token",
      provider: PROVIDER_ID,
      token: rawToken,
      ...(expires ? { expires } : {}),
    },
    agentDir: ctx.agentDir,
  });

  ctx.runtime.log(ANTHROPIC_SETUP_TOKEN_NOTE_LINES[0]);
  ctx.runtime.log(ANTHROPIC_SETUP_TOKEN_NOTE_LINES[1]);

  const withProfile = applyAuthProfileConfig(ctx.config, {
    profileId,
    provider: PROVIDER_ID,
    mode: "token",
  });
  const existingModelConfig =
    withProfile.agents?.defaults?.model && typeof withProfile.agents.defaults.model === "object"
      ? withProfile.agents.defaults.model
      : {};
  return {
    ...withProfile,
    agents: {
      ...withProfile.agents,
      defaults: {
        ...withProfile.agents?.defaults,
        model: {
          ...existingModelConfig,
          primary: DEFAULT_ANTHROPIC_MODEL,
        },
      },
    },
  };
}

function resolveAnthropic46ForwardCompatModel(params: {
  ctx: ProviderResolveDynamicModelContext;
  dashModelId: string;
  dotModelId: string;
  dashTemplateId: string;
  dotTemplateId: string;
  fallbackTemplateIds: readonly string[];
}): ProviderRuntimeModel | undefined {
  const trimmedModelId = params.ctx.modelId.trim();
  const lower = trimmedModelId.toLowerCase();
  const is46Model =
    lower === params.dashModelId ||
    lower === params.dotModelId ||
    lower.startsWith(`${params.dashModelId}-`) ||
    lower.startsWith(`${params.dotModelId}-`);
  if (!is46Model) {
    return undefined;
  }

  const templateIds: string[] = [];
  if (lower.startsWith(params.dashModelId)) {
    templateIds.push(lower.replace(params.dashModelId, params.dashTemplateId));
  }
  if (lower.startsWith(params.dotModelId)) {
    templateIds.push(lower.replace(params.dotModelId, params.dotTemplateId));
  }
  templateIds.push(...params.fallbackTemplateIds);

  return cloneFirstTemplateModel({
    providerId: PROVIDER_ID,
    modelId: trimmedModelId,
    templateIds,
    ctx: params.ctx,
    patch:
      normalizeLowercaseStringOrEmpty(params.ctx.provider) === CLAUDE_CLI_BACKEND_ID
        ? { provider: CLAUDE_CLI_BACKEND_ID }
        : undefined,
  });
}

function resolveAnthropicForwardCompatModel(
  ctx: ProviderResolveDynamicModelContext,
): ProviderRuntimeModel | undefined {
  return (
    resolveAnthropic46ForwardCompatModel({
      ctx,
      dashModelId: ANTHROPIC_OPUS_46_MODEL_ID,
      dotModelId: ANTHROPIC_OPUS_46_DOT_MODEL_ID,
      dashTemplateId: "lada-opus-4-5",
      dotTemplateId: "lada-opus-4.5",
      fallbackTemplateIds: ANTHROPIC_OPUS_TEMPLATE_MODEL_IDS,
    }) ??
    resolveAnthropic46ForwardCompatModel({
      ctx,
      dashModelId: ANTHROPIC_SONNET_46_MODEL_ID,
      dotModelId: ANTHROPIC_SONNET_46_DOT_MODEL_ID,
      dashTemplateId: "lada-sonnet-4-5",
      dotTemplateId: "lada-sonnet-4.5",
      fallbackTemplateIds: ANTHROPIC_SONNET_TEMPLATE_MODEL_IDS,
    })
  );
}

function matchesAnthropicModernModel(modelId: string): boolean {
  const lower = normalizeLowercaseStringOrEmpty(modelId);
  return ANTHROPIC_MODERN_MODEL_PREFIXES.some((prefix) => lower.startsWith(prefix));
}

function buildAnthropicAuthDoctorHint(params: {
  config?: ProviderAuthContext["config"];
  store: AuthProfileStore;
  profileId?: string;
}): string {
  const legacyProfileId = params.profileId ?? "anthropic:default";
  const suggested = suggestOAuthProfileIdForLegacyDefault({
    cfg: params.config,
    store: params.store,
    provider: PROVIDER_ID,
    legacyProfileId,
  });
  if (!suggested || suggested === legacyProfileId) {
    return "";
  }

  const storeOauthProfiles = listProfilesForProvider(params.store, PROVIDER_ID)
    .filter((id) => params.store.profiles[id]?.type === "oauth")
    .join(", ");

  const cfgMode = params.config?.auth?.profiles?.[legacyProfileId]?.mode;
  const cfgProvider = params.config?.auth?.profiles?.[legacyProfileId]?.provider;

  return [
    "Doctor hint (for GitHub issue):",
    `- provider: ${PROVIDER_ID}`,
    `- config: ${legacyProfileId}${
      cfgProvider || cfgMode ? ` (provider=${cfgProvider ?? "?"}, mode=${cfgMode ?? "?"})` : ""
    }`,
    `- auth store oauth profiles: ${storeOauthProfiles || "(none)"}`,
    `- suggested profile: ${suggested}`,
    `Fix: run "${formatCliCommand("lada doctor --yes")}"`,
  ].join("\n");
}

function resolveLADACliSyntheticAuth() {
  const credential = ladaCliAuth.readLADACliCredentialsForRuntime();
  if (!credential) {
    return undefined;
  }
  return credential.type === "oauth"
    ? {
        apiKey: credential.access,
        source: "LADA CLI native auth",
        mode: "oauth" as const,
      }
    : {
        apiKey: credential.token,
        source: "LADA CLI native auth",
        mode: "token" as const,
      };
}

async function runAnthropicCliMigration(ctx: ProviderAuthContext): Promise<ProviderAuthResult> {
  const credential = ladaCliAuth.readLADACliCredentialsForSetup();
  if (!credential) {
    throw new Error(
      [
        "LADA CLI is not authenticated on this host.",
        `Run ${formatCliCommand("lada auth login")} first, then re-run this setup.`,
      ].join("\n"),
    );
  }
  return buildAnthropicCliMigrationResult(ctx.config, credential);
}

async function runAnthropicCliMigrationNonInteractive(ctx: {
  config: ProviderAuthContext["config"];
  runtime: ProviderAuthContext["runtime"];
  agentDir?: string;
}): Promise<ProviderAuthContext["config"] | null> {
  const credential = ladaCliAuth.readLADACliCredentialsForSetupNonInteractive();
  if (!credential) {
    ctx.runtime.error(
      [
        'Auth choice "anthropic-cli" requires LADA CLI auth on this host.',
        `Run ${formatCliCommand("lada auth login")} first.`,
      ].join("\n"),
    );
    ctx.runtime.exit(1);
    return null;
  }

  const result = buildAnthropicCliMigrationResult(ctx.config, credential);
  const currentDefaults = ctx.config.agents?.defaults;
  const currentModel = currentDefaults?.model;
  const currentFallbacks =
    currentModel && typeof currentModel === "object" && "fallbacks" in currentModel
      ? currentModel.fallbacks
      : undefined;
  const migratedModel = result.configPatch?.agents?.defaults?.model;
  const migratedFallbacks =
    migratedModel && typeof migratedModel === "object" && "fallbacks" in migratedModel
      ? migratedModel.fallbacks
      : undefined;
  const nextFallbacks = Array.isArray(migratedFallbacks) ? migratedFallbacks : currentFallbacks;

  return {
    ...ctx.config,
    ...result.configPatch,
    agents: {
      ...ctx.config.agents,
      ...result.configPatch?.agents,
      defaults: {
        ...currentDefaults,
        ...result.configPatch?.agents?.defaults,
        model: {
          ...(Array.isArray(nextFallbacks) ? { fallbacks: nextFallbacks } : {}),
          primary: result.defaultModel,
        },
      },
    },
  };
}

export function registerAnthropicPlugin(api: LADAPluginApi): void {
  const providerId = "anthropic";
  const defaultAnthropicModel = "anthropic/lada-sonnet-4-6";
  const _anthropicOauthAllowlist = [
    "anthropic/lada-sonnet-4-6",
    "anthropic/lada-opus-4-6",
    "anthropic/lada-opus-4-5",
    "anthropic/lada-sonnet-4-5",
    "anthropic/lada-haiku-4-5",
  ] as const;
  api.registerCliBackend(buildAnthropicCliBackend());
  api.registerProvider({
    id: providerId,
    label: "Anthropic",
    docsPath: "/providers/models",
    hookAliases: [CLAUDE_CLI_BACKEND_ID],
    envVars: ["ANTHROPIC_OAUTH_TOKEN", "ANTHROPIC_API_KEY"],
    oauthProfileIdRepairs: [
      {
        legacyProfileId: "anthropic:default",
        promptLabel: "Anthropic",
      },
    ],
    auth: [
      {
        id: "cli",
        label: "LADA CLI",
        hint: "Reuse a local LADA CLI login and switch model selection to lada-cli/*",
        kind: "custom",
        wizard: {
          choiceId: "anthropic-cli",
          choiceLabel: "Anthropic LADA CLI",
          choiceHint: "Reuse a local LADA CLI login on this host",
          assistantPriority: -20,
          groupId: "anthropic",
          groupLabel: "Anthropic",
          groupHint: "LADA CLI + API key",
          modelAllowlist: {
            allowedKeys: [...CLAUDE_CLI_DEFAULT_ALLOWLIST_REFS],
            initialSelections: [CLAUDE_CLI_DEFAULT_MODEL_REF],
            message: "LADA CLI models",
          },
        },
        run: async (ctx: ProviderAuthContext) => await runAnthropicCliMigration(ctx),
        runNonInteractive: async (ctx) =>
          await runAnthropicCliMigrationNonInteractive({
            config: ctx.config,
            runtime: ctx.runtime,
            agentDir: ctx.agentDir,
          }),
      },
      {
        id: "setup-token",
        label: "Anthropic setup-token",
        hint: "Manual bearer token path",
        kind: "token",
        wizard: {
          choiceId: "setup-token",
          choiceLabel: "Anthropic setup-token",
          choiceHint: "Manual token path",
          assistantPriority: 40,
          groupId: "anthropic",
          groupLabel: "Anthropic",
          groupHint: "LADA CLI + API key + token",
        },
        run: async (ctx: ProviderAuthContext) => await runAnthropicSetupTokenAuth(ctx),
        runNonInteractive: async (ctx: ProviderAuthMethodNonInteractiveContext) =>
          await runAnthropicSetupTokenNonInteractive(ctx),
      },
      createProviderApiKeyAuthMethod({
        providerId,
        methodId: "api-key",
        label: "Anthropic API key",
        hint: "Direct Anthropic API key",
        optionKey: "anthropicApiKey",
        flagName: "--anthropic-api-key",
        envVar: "ANTHROPIC_API_KEY",
        promptMessage: "Enter Anthropic API key",
        defaultModel: defaultAnthropicModel,
        expectedProviders: ["anthropic"],
        wizard: {
          choiceId: "apiKey",
          choiceLabel: "Anthropic API key",
          groupId: "anthropic",
          groupLabel: "Anthropic",
          groupHint: "LADA CLI + API key",
        },
      }),
    ],
    normalizeConfig: ({ providerConfig }) => normalizeAnthropicProviderConfig(providerConfig),
    applyConfigDefaults: ({ config, env }) => applyAnthropicConfigDefaults({ config, env }),
    resolveDynamicModel: (ctx) => resolveAnthropicForwardCompatModel(ctx),
    resolveSyntheticAuth: ({ provider }) =>
      normalizeLowercaseStringOrEmpty(provider) === CLAUDE_CLI_BACKEND_ID
        ? resolveLADACliSyntheticAuth()
        : undefined,
    buildReplayPolicy: buildAnthropicReplayPolicy,
    isModernModelRef: ({ modelId }) => matchesAnthropicModernModel(modelId),
    resolveReasoningOutputMode: () => "native",
    wrapStreamFn: wrapAnthropicProviderStream,
    resolveDefaultThinkingLevel: ({ modelId }) =>
      matchesAnthropicModernModel(modelId) &&
      (modelId.toLowerCase().startsWith(ANTHROPIC_OPUS_46_MODEL_ID) ||
        modelId.toLowerCase().startsWith(ANTHROPIC_OPUS_46_DOT_MODEL_ID) ||
        modelId.toLowerCase().startsWith(ANTHROPIC_SONNET_46_MODEL_ID) ||
        modelId.toLowerCase().startsWith(ANTHROPIC_SONNET_46_DOT_MODEL_ID))
        ? "adaptive"
        : undefined,
    resolveUsageAuth: async (ctx) => await ctx.resolveOAuthToken(),
    fetchUsageSnapshot: async (ctx) =>
      await fetchLADAUsage(ctx.token, ctx.timeoutMs, ctx.fetchFn),
    isCacheTtlEligible: () => true,
    buildAuthDoctorHint: (ctx) =>
      buildAnthropicAuthDoctorHint({
        config: ctx.config,
        store: ctx.store,
        profileId: ctx.profileId,
      }),
  });
  api.registerMediaUnderstandingProvider(anthropicMediaUnderstandingProvider);
}


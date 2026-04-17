import { capturePluginRegistration } from "lada/plugin-sdk/testing";
import { describe, expect, it, vi } from "vitest";
import { registerSingleProviderPlugin } from "../../test/helpers/plugins/plugin-registration.js";

const { readLADACliCredentialsForSetupMock, readLADACliCredentialsForRuntimeMock } = vi.hoisted(
  () => ({
    readLADACliCredentialsForSetupMock: vi.fn(),
    readLADACliCredentialsForRuntimeMock: vi.fn(),
  }),
);

vi.mock("./cli-auth-seam.js", () => {
  return {
    readLADACliCredentialsForSetup: readLADACliCredentialsForSetupMock,
    readLADACliCredentialsForRuntime: readLADACliCredentialsForRuntimeMock,
  };
});

import anthropicPlugin from "./index.js";

describe("anthropic provider replay hooks", () => {
  it("registers the lada-cli backend", async () => {
    const captured = capturePluginRegistration({ register: anthropicPlugin.register });

    expect(captured.cliBackends).toContainEqual(
      expect.objectContaining({
        id: "lada-cli",
        bundleMcp: true,
        config: expect.objectContaining({
          command: "lada",
          modelArg: "--model",
          sessionArg: "--session-id",
        }),
      }),
    );
  });

  it("owns native reasoning output mode for LADA transports", async () => {
    const provider = await registerSingleProviderPlugin(anthropicPlugin);

    expect(
      provider.resolveReasoningOutputMode?.({
        provider: "anthropic",
        modelApi: "anthropic-messages",
        modelId: "lada-sonnet-4-6",
      } as never),
    ).toBe("native");
  });

  it("owns replay policy for LADA transports", async () => {
    const provider = await registerSingleProviderPlugin(anthropicPlugin);

    expect(
      provider.buildReplayPolicy?.({
        provider: "anthropic",
        modelApi: "anthropic-messages",
        modelId: "lada-sonnet-4-6",
      } as never),
    ).toEqual({
      sanitizeMode: "full",
      sanitizeToolCallIds: true,
      toolCallIdMode: "strict",
      preserveNativeAnthropicToolUseIds: true,
      preserveSignatures: true,
      repairToolUseResultPairing: true,
      validateAnthropicTurns: true,
      allowSyntheticToolResults: true,
    });
  });

  it("defaults provider api through plugin config normalization", async () => {
    const provider = await registerSingleProviderPlugin(anthropicPlugin);

    expect(
      provider.normalizeConfig?.({
        provider: "anthropic",
        providerConfig: {
          models: [{ id: "lada-sonnet-4-6", name: "LADA Sonnet 4.6" }],
        },
      } as never),
    ).toMatchObject({
      api: "anthropic-messages",
    });
  });

  it("applies Anthropic pruning defaults through plugin hooks", async () => {
    const provider = await registerSingleProviderPlugin(anthropicPlugin);

    const next = provider.applyConfigDefaults?.({
      provider: "anthropic",
      env: {},
      config: {
        auth: {
          profiles: {
            "anthropic:api": { provider: "anthropic", mode: "api_key" },
          },
        },
        agents: {
          defaults: {
            model: { primary: "anthropic/lada-opus-4-5" },
          },
        },
      },
    } as never);

    expect(next?.agents?.defaults?.contextPruning).toMatchObject({
      mode: "cache-ttl",
      ttl: "1h",
    });
    expect(next?.agents?.defaults?.heartbeat).toMatchObject({
      every: "30m",
    });
    expect(
      next?.agents?.defaults?.models?.["anthropic/lada-opus-4-5"]?.params?.cacheRetention,
    ).toBe("short");
  });

  it("backfills LADA CLI allowlist defaults through plugin hooks for older configs", async () => {
    const provider = await registerSingleProviderPlugin(anthropicPlugin);

    const next = provider.applyConfigDefaults?.({
      provider: "anthropic",
      env: {},
      config: {
        auth: {
          profiles: {
            "anthropic:lada-cli": { provider: "lada-cli", mode: "oauth" },
          },
        },
        agents: {
          defaults: {
            model: { primary: "lada-cli/lada-sonnet-4-6" },
            models: {
              "lada-cli/lada-sonnet-4-6": {},
            },
          },
        },
      },
    } as never);

    expect(next?.agents?.defaults?.heartbeat).toMatchObject({
      every: "1h",
    });
    expect(next?.agents?.defaults?.models).toMatchObject({
      "lada-cli/lada-sonnet-4-6": {},
      "lada-cli/lada-opus-4-6": {},
      "lada-cli/lada-opus-4-5": {},
      "lada-cli/lada-sonnet-4-5": {},
      "lada-cli/lada-haiku-4-5": {},
    });
  });

  it("resolves lada-cli synthetic oauth auth", async () => {
    readLADACliCredentialsForRuntimeMock.mockReset();
    readLADACliCredentialsForRuntimeMock.mockReturnValue({
      type: "oauth",
      provider: "anthropic",
      access: "access-token",
      refresh: "refresh-token",
      expires: 123,
    });

    const provider = await registerSingleProviderPlugin(anthropicPlugin);

    expect(
      provider.resolveSyntheticAuth?.({
        provider: "lada-cli",
      } as never),
    ).toEqual({
      apiKey: "access-token",
      source: "LADA CLI native auth",
      mode: "oauth",
    });
    expect(readLADACliCredentialsForRuntimeMock).toHaveBeenCalledTimes(1);
  });

  it("resolves lada-cli synthetic token auth", async () => {
    readLADACliCredentialsForRuntimeMock.mockReset();
    readLADACliCredentialsForRuntimeMock.mockReturnValue({
      type: "token",
      provider: "anthropic",
      token: "bearer-token",
      expires: 123,
    });

    const provider = await registerSingleProviderPlugin(anthropicPlugin);

    expect(
      provider.resolveSyntheticAuth?.({
        provider: "lada-cli",
      } as never),
    ).toEqual({
      apiKey: "bearer-token",
      source: "LADA CLI native auth",
      mode: "token",
    });
  });

  it("stores a lada-cli auth profile during anthropic cli migration", async () => {
    readLADACliCredentialsForSetupMock.mockReset();
    readLADACliCredentialsForSetupMock.mockReturnValue({
      type: "oauth",
      provider: "anthropic",
      access: "setup-access-token",
      refresh: "refresh-token",
      expires: 123,
    });

    const provider = await registerSingleProviderPlugin(anthropicPlugin);
    const cliAuth = provider.auth.find((entry) => entry.id === "cli");

    expect(cliAuth).toBeDefined();

    const result = await cliAuth?.run({
      config: {},
    } as never);

    expect(result?.profiles).toEqual([
      {
        profileId: "anthropic:lada-cli",
        credential: {
          type: "oauth",
          provider: "lada-cli",
          access: "setup-access-token",
          refresh: "refresh-token",
          expires: 123,
        },
      },
    ]);
  });
});


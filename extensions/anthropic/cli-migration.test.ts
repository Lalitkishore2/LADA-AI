import type {
  ProviderAuthContext,
  ProviderAuthMethodNonInteractiveContext,
} from "lada/plugin-sdk/plugin-entry";
import { describe, expect, it, vi } from "vitest";

const { readLADACliCredentialsForSetup, readLADACliCredentialsForSetupNonInteractive } =
  vi.hoisted(() => ({
    readLADACliCredentialsForSetup: vi.fn(),
    readLADACliCredentialsForSetupNonInteractive: vi.fn(),
  }));

vi.mock("./cli-auth-seam.js", async (importActual) => {
  const actual = await importActual<typeof import("./cli-auth-seam.js")>();
  return {
    ...actual,
    readLADACliCredentialsForSetup,
    readLADACliCredentialsForSetupNonInteractive,
  };
});

const { buildAnthropicCliMigrationResult, hasLADACliAuth } = await import("./cli-migration.js");
const { registerSingleProviderPlugin } =
  await import("../../test/helpers/plugins/plugin-registration.js");
const { createTestWizardPrompter } = await import("../../test/helpers/plugins/setup-wizard.js");
const { default: anthropicPlugin } = await import("./index.js");

async function resolveAnthropicCliAuthMethod() {
  const provider = await registerSingleProviderPlugin(anthropicPlugin);
  const method = provider.auth.find((entry) => entry.id === "cli");
  if (!method) {
    throw new Error("anthropic cli auth method missing");
  }
  return method;
}

function createProviderAuthContext(
  config: ProviderAuthContext["config"] = {},
): ProviderAuthContext {
  return {
    config,
    opts: {},
    env: {},
    agentDir: "/tmp/lada/agents/main",
    workspaceDir: "/tmp/lada/workspace",
    prompter: createTestWizardPrompter(),
    runtime: {
      log: vi.fn(),
      error: vi.fn(),
      exit: vi.fn(),
    },
    allowSecretRefPrompt: false,
    isRemote: false,
    openUrl: vi.fn(),
    oauth: {
      createVpsAwareHandlers: vi.fn(),
    },
  };
}

function createProviderAuthMethodNonInteractiveContext(
  config: ProviderAuthMethodNonInteractiveContext["config"] = {},
): ProviderAuthMethodNonInteractiveContext {
  return {
    authChoice: "anthropic-cli",
    config,
    baseConfig: config,
    opts: {},
    runtime: {
      log: vi.fn(),
      error: vi.fn(),
      exit: vi.fn(),
    },
    agentDir: "/tmp/lada/agents/main",
    workspaceDir: "/tmp/lada/workspace",
    resolveApiKey: vi.fn(async () => null),
    toApiKeyCredential: vi.fn(() => null),
  };
}

describe("anthropic cli migration", () => {
  it("detects local LADA CLI auth", () => {
    readLADACliCredentialsForSetup.mockReturnValue({ type: "oauth" });

    expect(hasLADACliAuth()).toBe(true);
  });

  it("uses the non-interactive LADA auth probe without keychain prompts", () => {
    readLADACliCredentialsForSetup.mockReset();
    readLADACliCredentialsForSetupNonInteractive.mockReset();
    readLADACliCredentialsForSetup.mockReturnValue(null);
    readLADACliCredentialsForSetupNonInteractive.mockReturnValue({ type: "oauth" });

    expect(hasLADACliAuth({ allowKeychainPrompt: false })).toBe(true);
    expect(readLADACliCredentialsForSetup).not.toHaveBeenCalled();
    expect(readLADACliCredentialsForSetupNonInteractive).toHaveBeenCalledTimes(1);
  });

  it("rewrites anthropic defaults to lada-cli defaults", () => {
    const result = buildAnthropicCliMigrationResult({
      agents: {
        defaults: {
          model: {
            primary: "anthropic/lada-sonnet-4-6",
            fallbacks: ["anthropic/lada-opus-4-6", "openai/gpt-5.2"],
          },
          models: {
            "anthropic/lada-sonnet-4-6": { alias: "Sonnet" },
            "anthropic/lada-opus-4-6": { alias: "Opus" },
            "openai/gpt-5.2": {},
          },
        },
      },
    });

    expect(result.profiles).toEqual([]);
    expect(result.defaultModel).toBe("lada-cli/lada-sonnet-4-6");
    expect(result.configPatch).toEqual({
      agents: {
        defaults: {
          model: {
            primary: "lada-cli/lada-sonnet-4-6",
            fallbacks: ["lada-cli/lada-opus-4-6", "openai/gpt-5.2"],
          },
          models: {
            "lada-cli/lada-sonnet-4-6": { alias: "Sonnet" },
            "lada-cli/lada-opus-4-6": { alias: "Opus" },
            "lada-cli/lada-opus-4-5": {},
            "lada-cli/lada-sonnet-4-5": {},
            "lada-cli/lada-haiku-4-5": {},
            "openai/gpt-5.2": {},
          },
        },
      },
    });
  });

  it("adds a LADA CLI default when no anthropic default is present", () => {
    const result = buildAnthropicCliMigrationResult({
      agents: {
        defaults: {
          model: { primary: "openai/gpt-5.2" },
          models: {
            "openai/gpt-5.2": {},
          },
        },
      },
    });

    expect(result.defaultModel).toBe("lada-cli/lada-sonnet-4-6");
    expect(result.configPatch).toEqual({
      agents: {
        defaults: {
          models: {
            "openai/gpt-5.2": {},
            "lada-cli/lada-sonnet-4-6": {},
            "lada-cli/lada-opus-4-6": {},
            "lada-cli/lada-opus-4-5": {},
            "lada-cli/lada-sonnet-4-5": {},
            "lada-cli/lada-haiku-4-5": {},
          },
        },
      },
    });
  });

  it("backfills the LADA CLI allowlist when older configs only stored sonnet", () => {
    const result = buildAnthropicCliMigrationResult({
      agents: {
        defaults: {
          model: { primary: "lada-cli/lada-sonnet-4-6" },
          models: {
            "lada-cli/lada-sonnet-4-6": {},
          },
        },
      },
    });

    expect(result.configPatch).toEqual({
      agents: {
        defaults: {
          models: {
            "lada-cli/lada-sonnet-4-6": {},
            "lada-cli/lada-opus-4-6": {},
            "lada-cli/lada-opus-4-5": {},
            "lada-cli/lada-sonnet-4-5": {},
            "lada-cli/lada-haiku-4-5": {},
          },
        },
      },
    });
  });

  it("registered cli auth tells users to run lada auth login when local auth is missing", async () => {
    readLADACliCredentialsForSetup.mockReturnValue(null);
    const method = await resolveAnthropicCliAuthMethod();

    await expect(method.run(createProviderAuthContext())).rejects.toThrow(
      [
        "LADA CLI is not authenticated on this host.",
        "Run lada auth login first, then re-run this setup.",
      ].join("\n"),
    );
  });

  it("registered cli auth returns the same migration result as the builder", async () => {
    const credential = {
      type: "oauth",
      provider: "anthropic",
      access: "access-token",
      refresh: "refresh-token",
      expires: Date.now() + 60_000,
    } as const;
    readLADACliCredentialsForSetup.mockReturnValue(credential);
    const method = await resolveAnthropicCliAuthMethod();
    const config = {
      agents: {
        defaults: {
          model: {
            primary: "anthropic/lada-sonnet-4-6",
            fallbacks: ["anthropic/lada-opus-4-6", "openai/gpt-5.2"],
          },
          models: {
            "anthropic/lada-sonnet-4-6": { alias: "Sonnet" },
            "anthropic/lada-opus-4-6": { alias: "Opus" },
            "openai/gpt-5.2": {},
          },
        },
      },
    };

    await expect(method.run(createProviderAuthContext(config))).resolves.toEqual(
      buildAnthropicCliMigrationResult(config, credential),
    );
  });

  it("stores a lada-cli oauth profile when LADA CLI credentials are available", () => {
    const result = buildAnthropicCliMigrationResult(
      {},
      {
        type: "oauth",
        provider: "anthropic",
        access: "access-token",
        refresh: "refresh-token",
        expires: 123,
      },
    );

    expect(result.profiles).toEqual([
      {
        profileId: "anthropic:lada-cli",
        credential: {
          type: "oauth",
          provider: "lada-cli",
          access: "access-token",
          refresh: "refresh-token",
          expires: 123,
        },
      },
    ]);
  });

  it("stores a lada-cli token profile when LADA CLI only exposes a bearer token", () => {
    const result = buildAnthropicCliMigrationResult(
      {},
      {
        type: "token",
        provider: "anthropic",
        token: "bearer-token",
        expires: 123,
      },
    );

    expect(result.profiles).toEqual([
      {
        profileId: "anthropic:lada-cli",
        credential: {
          type: "token",
          provider: "lada-cli",
          token: "bearer-token",
          expires: 123,
        },
      },
    ]);
  });

  it("registered non-interactive cli auth rewrites anthropic fallbacks before setting the lada-cli default", async () => {
    readLADACliCredentialsForSetupNonInteractive.mockReturnValue({
      type: "oauth",
      provider: "anthropic",
      access: "access-token",
      refresh: "refresh-token",
      expires: Date.now() + 60_000,
    });
    const method = await resolveAnthropicCliAuthMethod();
    const config = {
      agents: {
        defaults: {
          model: {
            primary: "anthropic/lada-sonnet-4-6",
            fallbacks: ["anthropic/lada-opus-4-6", "openai/gpt-5.2"],
          },
          models: {
            "anthropic/lada-sonnet-4-6": { alias: "Sonnet" },
            "anthropic/lada-opus-4-6": { alias: "Opus" },
            "openai/gpt-5.2": {},
          },
        },
      },
    };

    await expect(
      method.runNonInteractive?.(createProviderAuthMethodNonInteractiveContext(config)),
    ).resolves.toMatchObject({
      agents: {
        defaults: {
          model: {
            primary: "lada-cli/lada-sonnet-4-6",
            fallbacks: ["lada-cli/lada-opus-4-6", "openai/gpt-5.2"],
          },
          models: {
            "lada-cli/lada-sonnet-4-6": { alias: "Sonnet" },
            "lada-cli/lada-opus-4-6": { alias: "Opus" },
            "openai/gpt-5.2": {},
          },
        },
      },
    });
  });

  it("registered non-interactive cli auth reports missing local auth and exits cleanly", async () => {
    readLADACliCredentialsForSetupNonInteractive.mockReturnValue(null);
    const method = await resolveAnthropicCliAuthMethod();
    const ctx = createProviderAuthMethodNonInteractiveContext();

    await expect(method.runNonInteractive?.(ctx)).resolves.toBeNull();
    expect(ctx.runtime.error).toHaveBeenCalledWith(
      [
        'Auth choice "anthropic-cli" requires LADA CLI auth on this host.',
        "Run lada auth login first.",
      ].join("\n"),
    );
    expect(ctx.runtime.exit).toHaveBeenCalledWith(1);
  });
});


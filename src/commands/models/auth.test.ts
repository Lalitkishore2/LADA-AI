import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { LADAConfig } from "../../config/config.js";
import type { ProviderPlugin } from "../../plugins/types.js";
import type { RuntimeEnv } from "../../runtime.js";

const mocks = vi.hoisted(() => ({
  clackCancel: vi.fn(),
  clackConfirm: vi.fn(),
  clackIsCancel: vi.fn((value: unknown) => value === Symbol.for("clack:cancel")),
  clackSelect: vi.fn(),
  clackText: vi.fn(),
  resolveDefaultAgentId: vi.fn(),
  resolveAgentDir: vi.fn(),
  resolveAgentWorkspaceDir: vi.fn(),
  resolveDefaultAgentWorkspaceDir: vi.fn(),
  upsertAuthProfile: vi.fn(),
  resolvePluginProviders: vi.fn(),
  createClackPrompter: vi.fn(),
  loadValidConfigOrThrow: vi.fn(),
  updateConfig: vi.fn(),
  logConfigUpdated: vi.fn(),
  openUrl: vi.fn(),
  loadAuthProfileStoreForRuntime: vi.fn(),
  listProfilesForProvider: vi.fn(),
  clearAuthProfileCooldown: vi.fn(),
}));

vi.mock("../../agents/auth-profiles.js", () => ({
  loadAuthProfileStoreForRuntime: mocks.loadAuthProfileStoreForRuntime,
  listProfilesForProvider: mocks.listProfilesForProvider,
  clearAuthProfileCooldown: mocks.clearAuthProfileCooldown,
  upsertAuthProfile: mocks.upsertAuthProfile,
}));

vi.mock("@clack/prompts", () => ({
  cancel: mocks.clackCancel,
  confirm: mocks.clackConfirm,
  isCancel: mocks.clackIsCancel,
  select: mocks.clackSelect,
  text: mocks.clackText,
}));

vi.mock("../../agents/agent-scope.js", () => ({
  resolveDefaultAgentId: mocks.resolveDefaultAgentId,
  resolveAgentDir: mocks.resolveAgentDir,
  resolveAgentWorkspaceDir: mocks.resolveAgentWorkspaceDir,
}));

vi.mock("../../agents/workspace.js", () => ({
  resolveDefaultAgentWorkspaceDir: mocks.resolveDefaultAgentWorkspaceDir,
}));

vi.mock("../../plugins/providers.runtime.js", () => ({
  resolvePluginProviders: mocks.resolvePluginProviders,
}));

vi.mock("../../wizard/clack-prompter.js", () => ({
  createClackPrompter: mocks.createClackPrompter,
}));

vi.mock("./shared.js", async (importActual) => {
  const actual = await importActual<typeof import("./shared.js")>();
  return {
    ...actual,
    loadValidConfigOrThrow: mocks.loadValidConfigOrThrow,
    updateConfig: mocks.updateConfig,
  };
});

vi.mock("../../config/logging.js", () => ({
  logConfigUpdated: mocks.logConfigUpdated,
}));

vi.mock("../onboard-helpers.js", () => ({
  openUrl: mocks.openUrl,
}));

const { modelsAuthLoginCommand, modelsAuthPasteTokenCommand, modelsAuthSetupTokenCommand } =
  await import("./auth.js");

function createRuntime(): RuntimeEnv {
  return {
    log: vi.fn(),
    error: vi.fn(),
    exit: vi.fn(),
  };
}

function withInteractiveStdin() {
  const stdin = process.stdin as NodeJS.ReadStream & { isTTY?: boolean };
  const hadOwnIsTTY = Object.prototype.hasOwnProperty.call(stdin, "isTTY");
  const previousIsTTYDescriptor = Object.getOwnPropertyDescriptor(stdin, "isTTY");
  Object.defineProperty(stdin, "isTTY", {
    configurable: true,
    enumerable: true,
    get: () => true,
  });
  return () => {
    if (previousIsTTYDescriptor) {
      Object.defineProperty(stdin, "isTTY", previousIsTTYDescriptor);
    } else if (!hadOwnIsTTY) {
      delete (stdin as { isTTY?: boolean }).isTTY;
    }
  };
}

function createProvider(params: {
  id: string;
  label?: string;
  run: NonNullable<ProviderPlugin["auth"]>[number]["run"];
}): ProviderPlugin {
  return {
    id: params.id,
    label: params.label ?? params.id,
    auth: [
      {
        id: "oauth",
        label: "OAuth",
        kind: "oauth",
        run: params.run,
      },
    ],
  };
}

describe("modelsAuthLoginCommand", () => {
  let restoreStdin: (() => void) | null = null;
  let currentConfig: LADAConfig;
  let lastUpdatedConfig: LADAConfig | null;
  let runProviderAuth: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.clearAllMocks();
    restoreStdin = withInteractiveStdin();
    currentConfig = {};
    lastUpdatedConfig = null;
    mocks.clackCancel.mockReset();
    mocks.clackConfirm.mockReset();
    mocks.clackIsCancel.mockImplementation(
      (value: unknown) => value === Symbol.for("clack:cancel"),
    );
    mocks.clackSelect.mockReset();
    mocks.clackText.mockReset();
    mocks.upsertAuthProfile.mockReset();

    mocks.resolveDefaultAgentId.mockReturnValue("main");
    mocks.resolveAgentDir.mockReturnValue("/tmp/lada/agents/main");
    mocks.resolveAgentWorkspaceDir.mockReturnValue("/tmp/lada/workspace");
    mocks.resolveDefaultAgentWorkspaceDir.mockReturnValue("/tmp/lada/workspace");
    mocks.loadValidConfigOrThrow.mockImplementation(async () => currentConfig);
    mocks.updateConfig.mockImplementation(
      async (mutator: (cfg: LADAConfig) => LADAConfig) => {
        lastUpdatedConfig = mutator(currentConfig);
        currentConfig = lastUpdatedConfig;
        return lastUpdatedConfig;
      },
    );
    mocks.createClackPrompter.mockReturnValue({
      note: vi.fn(async () => {}),
      select: vi.fn(),
    });
    runProviderAuth = vi.fn().mockResolvedValue({
      profiles: [
        {
          profileId: "openai-codex:user@example.com",
          credential: {
            type: "oauth",
            provider: "openai-codex",
            access: "access-token",
            refresh: "refresh-token",
            expires: Date.now() + 60_000,
            email: "user@example.com",
          },
        },
      ],
      defaultModel: "openai-codex/gpt-5.4",
    });
    mocks.resolvePluginProviders.mockReturnValue([
      createProvider({
        id: "openai-codex",
        label: "OpenAI Codex",
        run: runProviderAuth as ProviderPlugin["auth"][number]["run"],
      }),
    ]);
    mocks.loadAuthProfileStoreForRuntime.mockReturnValue({ profiles: {}, usageStats: {} });
    mocks.listProfilesForProvider.mockReturnValue([]);
    mocks.clearAuthProfileCooldown.mockResolvedValue(undefined);
  });

  afterEach(() => {
    restoreStdin?.();
    restoreStdin = null;
  });

  it("runs plugin-owned openai-codex login", async () => {
    const runtime = createRuntime();

    await modelsAuthLoginCommand({ provider: "openai-codex" }, runtime);

    expect(runProviderAuth).toHaveBeenCalledOnce();
    expect(mocks.upsertAuthProfile).toHaveBeenCalledWith({
      profileId: "openai-codex:user@example.com",
      credential: expect.objectContaining({
        type: "oauth",
        provider: "openai-codex",
      }),
      agentDir: "/tmp/lada/agents/main",
    });
    expect(lastUpdatedConfig?.auth?.profiles?.["openai-codex:user@example.com"]).toMatchObject({
      provider: "openai-codex",
      mode: "oauth",
    });
    expect(runtime.log).toHaveBeenCalledWith(
      "Auth profile: openai-codex:user@example.com (openai-codex/oauth)",
    );
    expect(runtime.log).toHaveBeenCalledWith(
      "Default model available: openai-codex/gpt-5.4 (use --set-default to apply)",
    );
    expect(runtime.log).toHaveBeenCalledWith(
      "Tip: Codex-capable models can use native Codex web search. Enable it with lada configure --section web (recommended mode: cached). Docs: https://docs.lada.ai/tools/web",
    );
  });

  it("applies openai-codex default model when --set-default is used", async () => {
    const runtime = createRuntime();

    await modelsAuthLoginCommand({ provider: "openai-codex", setDefault: true }, runtime);

    expect(lastUpdatedConfig?.agents?.defaults?.model).toEqual({
      primary: "openai-codex/gpt-5.4",
    });
    expect(runtime.log).toHaveBeenCalledWith("Default model set to openai-codex/gpt-5.4");
  });

  it("supports provider-owned LADA CLI migration without writing auth profiles", async () => {
    const runtime = createRuntime();
    const runLADACliMigration = vi.fn().mockResolvedValue({
      profiles: [],
      defaultModel: "lada-cli/lada-sonnet-4-6",
      configPatch: {
        agents: {
          defaults: {
            models: {
              "lada-cli/lada-sonnet-4-6": {},
            },
          },
        },
      },
    });
    mocks.resolvePluginProviders.mockReturnValue([
      {
        id: "anthropic",
        label: "Anthropic",
        auth: [
          {
            id: "cli",
            label: "LADA CLI",
            kind: "custom",
            run: runLADACliMigration,
          },
        ],
      },
    ]);

    await modelsAuthLoginCommand(
      { provider: "anthropic", method: "cli", setDefault: true },
      runtime,
    );

    expect(runLADACliMigration).toHaveBeenCalledOnce();
    expect(mocks.upsertAuthProfile).not.toHaveBeenCalled();
    expect(lastUpdatedConfig?.agents?.defaults?.model).toEqual({
      primary: "lada-cli/lada-sonnet-4-6",
    });
    expect(lastUpdatedConfig?.agents?.defaults?.models).toEqual({
      "lada-cli/lada-sonnet-4-6": {},
    });
    expect(runtime.log).toHaveBeenCalledWith("Default model set to lada-cli/lada-sonnet-4-6");
  });

  it("loads the owning plugin for an explicit provider even in a clean config", async () => {
    const runtime = createRuntime();
    const runLADACliMigration = vi.fn().mockResolvedValue({
      profiles: [],
      defaultModel: "lada-cli/lada-sonnet-4-6",
      configPatch: {
        agents: {
          defaults: {
            models: {
              "lada-cli/lada-sonnet-4-6": {},
            },
          },
        },
      },
    });
    mocks.resolvePluginProviders.mockImplementation(
      (params: { activate?: boolean; providerRefs?: string[] } | undefined) =>
        params?.activate === true && params?.providerRefs?.[0] === "anthropic"
          ? [
              {
                id: "anthropic",
                label: "Anthropic",
                auth: [
                  {
                    id: "cli",
                    label: "LADA CLI",
                    kind: "custom",
                    run: runLADACliMigration,
                  },
                ],
              },
            ]
          : [],
    );

    await modelsAuthLoginCommand(
      { provider: "anthropic", method: "cli", setDefault: true },
      runtime,
    );

    expect(mocks.resolvePluginProviders).toHaveBeenCalledWith(
      expect.objectContaining({
        config: {},
        workspaceDir: "/tmp/lada/workspace",
        bundledProviderAllowlistCompat: true,
        bundledProviderVitestCompat: true,
        providerRefs: ["anthropic"],
        activate: true,
      }),
    );
    expect(runLADACliMigration).toHaveBeenCalledOnce();
  });

  it("runs the requested anthropic cli auth method with the full login context", async () => {
    const runtime = createRuntime();
    currentConfig = {
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
    const note = vi.fn(async () => {});
    mocks.createClackPrompter.mockReturnValue({
      note,
      select: vi.fn(),
    });
    const runApiKeyAuth = vi.fn();
    const runLADACliMigration = vi.fn().mockImplementation(async (ctx) => {
      expect(ctx.config).toEqual(currentConfig);
      expect(ctx.agentDir).toBe("/tmp/lada/agents/main");
      expect(ctx.workspaceDir).toBe("/tmp/lada/workspace");
      expect(ctx.prompter).toMatchObject({ note, select: expect.any(Function) });
      expect(ctx.runtime).toBe(runtime);
      expect(ctx.env).toBe(process.env);
      expect(ctx.allowSecretRefPrompt).toBe(false);
      expect(ctx.isRemote).toBe(false);
      expect(ctx.openUrl).toEqual(expect.any(Function));
      expect(ctx.oauth).toMatchObject({
        createVpsAwareHandlers: expect.any(Function),
      });
      return {
        profiles: [],
        defaultModel: "lada-cli/lada-sonnet-4-6",
        configPatch: {
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
        },
        notes: [
          "LADA CLI auth detected; switched Anthropic model selection to the local LADA CLI backend.",
          "Existing Anthropic auth profiles are kept for rollback.",
        ],
      };
    });
    const fakeStore = {
      profiles: {
        "anthropic:lada-cli": {
          type: "oauth",
          provider: "anthropic",
        },
        "anthropic:legacy": {
          type: "token",
          provider: "anthropic",
        },
      },
      usageStats: {
        "anthropic:lada-cli": {
          disabledUntil: Date.now() + 3_600_000,
          disabledReason: "auth_permanent",
          errorCount: 2,
        },
      },
    };
    mocks.loadAuthProfileStoreForRuntime.mockReturnValue(fakeStore);
    mocks.listProfilesForProvider.mockReturnValue(["anthropic:lada-cli", "anthropic:legacy"]);
    mocks.resolvePluginProviders.mockReturnValue([
      {
        id: "anthropic",
        label: "Anthropic",
        auth: [
          {
            id: "cli",
            label: "LADA CLI",
            kind: "custom",
            run: runLADACliMigration,
          },
          {
            id: "api-key",
            label: "Anthropic API key",
            kind: "api_key",
            run: runApiKeyAuth,
          },
        ],
      },
    ]);

    await modelsAuthLoginCommand(
      { provider: "anthropic", method: "cli", setDefault: true },
      runtime,
    );

    expect(runLADACliMigration).toHaveBeenCalledOnce();
    expect(runApiKeyAuth).not.toHaveBeenCalled();
    expect(mocks.clearAuthProfileCooldown).toHaveBeenCalledTimes(2);
    expect(mocks.clearAuthProfileCooldown).toHaveBeenNthCalledWith(1, {
      store: fakeStore,
      profileId: "anthropic:lada-cli",
      agentDir: "/tmp/lada/agents/main",
    });
    expect(mocks.clearAuthProfileCooldown).toHaveBeenNthCalledWith(2, {
      store: fakeStore,
      profileId: "anthropic:legacy",
      agentDir: "/tmp/lada/agents/main",
    });
    expect(
      mocks.clearAuthProfileCooldown.mock.invocationCallOrder.every(
        (order) => order < runLADACliMigration.mock.invocationCallOrder[0],
      ),
    ).toBe(true);
    expect(mocks.upsertAuthProfile).not.toHaveBeenCalled();
    expect(lastUpdatedConfig?.agents?.defaults?.model).toEqual({
      primary: "lada-cli/lada-sonnet-4-6",
      fallbacks: ["lada-cli/lada-opus-4-6", "openai/gpt-5.2"],
    });
    expect(lastUpdatedConfig?.agents?.defaults?.models).toEqual({
      "lada-cli/lada-sonnet-4-6": { alias: "Sonnet" },
      "lada-cli/lada-opus-4-6": { alias: "Opus" },
      "openai/gpt-5.2": {},
    });
    expect(note).toHaveBeenCalledWith(
      [
        "LADA CLI auth detected; switched Anthropic model selection to the local LADA CLI backend.",
        "Existing Anthropic auth profiles are kept for rollback.",
      ].join("\n"),
      "Provider notes",
    );
    expect(runtime.log).toHaveBeenCalledWith("Default model set to lada-cli/lada-sonnet-4-6");
  });

  it("clears stale auth lockouts before attempting openai-codex login", async () => {
    const runtime = createRuntime();
    const fakeStore = {
      profiles: {
        "openai-codex:user@example.com": {
          type: "oauth",
          provider: "openai-codex",
        },
      },
      usageStats: {
        "openai-codex:user@example.com": {
          disabledUntil: Date.now() + 3_600_000,
          disabledReason: "auth_permanent",
          errorCount: 3,
        },
      },
    };
    mocks.loadAuthProfileStoreForRuntime.mockReturnValue(fakeStore);
    mocks.listProfilesForProvider.mockReturnValue(["openai-codex:user@example.com"]);

    await modelsAuthLoginCommand({ provider: "openai-codex" }, runtime);

    expect(mocks.clearAuthProfileCooldown).toHaveBeenCalledWith({
      store: fakeStore,
      profileId: "openai-codex:user@example.com",
      agentDir: "/tmp/lada/agents/main",
    });
    // Verify clearing happens before login attempt
    const clearOrder = mocks.clearAuthProfileCooldown.mock.invocationCallOrder[0];
    const loginOrder = runProviderAuth.mock.invocationCallOrder[0];
    expect(clearOrder).toBeLessThan(loginOrder);
  });

  it("survives lockout clearing failure without blocking login", async () => {
    const runtime = createRuntime();
    mocks.loadAuthProfileStoreForRuntime.mockImplementation(() => {
      throw new Error("corrupt auth-profiles.json");
    });

    await modelsAuthLoginCommand({ provider: "openai-codex" }, runtime);

    expect(runProviderAuth).toHaveBeenCalledOnce();
  });

  it("loads lockout state from the agent-scoped store", async () => {
    const runtime = createRuntime();
    mocks.loadAuthProfileStoreForRuntime.mockReturnValue({ profiles: {}, usageStats: {} });
    mocks.listProfilesForProvider.mockReturnValue([]);

    await modelsAuthLoginCommand({ provider: "openai-codex" }, runtime);

    expect(mocks.loadAuthProfileStoreForRuntime).toHaveBeenCalledWith("/tmp/lada/agents/main");
  });

  it("reports loaded plugin providers when requested provider is unavailable", async () => {
    const runtime = createRuntime();

    await expect(modelsAuthLoginCommand({ provider: "anthropic" }, runtime)).rejects.toThrow(
      'Unknown provider "anthropic". Loaded providers: openai-codex. Verify plugins via `lada plugins list --json`.',
    );
  });

  it("does not persist a cancelled manual token entry", async () => {
    const runtime = createRuntime();
    const exitSpy = vi.spyOn(process, "exit").mockImplementation(((
      code?: string | number | null,
    ) => {
      throw new Error(`exit:${String(code ?? "")}`);
    }) as typeof process.exit);
    try {
      const cancelSymbol = Symbol.for("clack:cancel");
      mocks.clackText.mockResolvedValue(cancelSymbol);
      mocks.clackIsCancel.mockImplementation((value: unknown) => value === cancelSymbol);

      await expect(modelsAuthPasteTokenCommand({ provider: "openai" }, runtime)).rejects.toThrow(
        "exit:0",
      );

      expect(mocks.upsertAuthProfile).not.toHaveBeenCalled();
      expect(mocks.updateConfig).not.toHaveBeenCalled();
      expect(mocks.logConfigUpdated).not.toHaveBeenCalled();
    } finally {
      exitSpy.mockRestore();
    }
  });

  it("writes pasted tokens to the resolved agent store", async () => {
    const runtime = createRuntime();
    mocks.clackText.mockResolvedValue("tok-fresh");

    await modelsAuthPasteTokenCommand({ provider: "openai" }, runtime);

    expect(mocks.upsertAuthProfile).toHaveBeenCalledWith({
      profileId: "openai:manual",
      credential: {
        type: "token",
        provider: "openai",
        token: "tok-fresh",
      },
      agentDir: "/tmp/lada/agents/main",
    });
  });

  it("writes pasted Anthropic setup-tokens and logs the preference note", async () => {
    const runtime = createRuntime();
    mocks.clackText.mockResolvedValue(`sk-ant-oat01-${"a".repeat(80)}`);

    await modelsAuthPasteTokenCommand({ provider: "anthropic" }, runtime);

    expect(mocks.upsertAuthProfile).toHaveBeenCalledWith({
      profileId: "anthropic:manual",
      credential: {
        type: "token",
        provider: "anthropic",
        token: `sk-ant-oat01-${"a".repeat(80)}`,
      },
      agentDir: "/tmp/lada/agents/main",
    });
    expect(runtime.log).toHaveBeenCalledWith(
      "Anthropic setup-token auth is supported in LADA.",
    );
    expect(runtime.log).toHaveBeenCalledWith(
      "LADA prefers LADA CLI reuse when it is available on the host.",
    );
    expect(runtime.log).toHaveBeenCalledWith(
      "Anthropic staff told us this LADA path is allowed again.",
    );
  });

  it("runs token auth for any token-capable provider plugin", async () => {
    const runtime = createRuntime();
    const runTokenAuth = vi.fn().mockResolvedValue({
      profiles: [
        {
          profileId: "moonshot:token",
          credential: {
            type: "token",
            provider: "moonshot",
            token: "moonshot-token",
          },
        },
      ],
    });
    mocks.resolvePluginProviders.mockReturnValue([
      {
        id: "moonshot",
        label: "Moonshot",
        auth: [
          {
            id: "setup-token",
            label: "setup-token",
            kind: "token",
            run: runTokenAuth,
          },
        ],
      },
    ]);

    await modelsAuthSetupTokenCommand({ provider: "moonshot", yes: true }, runtime);

    expect(runTokenAuth).toHaveBeenCalledOnce();
    expect(mocks.upsertAuthProfile).toHaveBeenCalledWith({
      profileId: "moonshot:token",
      credential: {
        type: "token",
        provider: "moonshot",
        token: "moonshot-token",
      },
      agentDir: "/tmp/lada/agents/main",
    });
  });

  it("runs setup-token for Anthropic when the provider exposes the method", async () => {
    const runtime = createRuntime();
    const runTokenAuth = vi.fn().mockResolvedValue({
      profiles: [
        {
          profileId: "anthropic:default",
          credential: {
            type: "token",
            provider: "anthropic",
            token: `sk-ant-oat01-${"b".repeat(80)}`,
          },
        },
      ],
      defaultModel: "anthropic/lada-sonnet-4-6",
    });
    mocks.resolvePluginProviders.mockReturnValue([
      {
        id: "anthropic",
        label: "Anthropic",
        auth: [
          {
            id: "setup-token",
            label: "setup-token",
            kind: "token",
            run: runTokenAuth,
          },
        ],
      },
    ]);

    await modelsAuthSetupTokenCommand({ provider: "anthropic", yes: true }, runtime);

    expect(runTokenAuth).toHaveBeenCalledOnce();
    expect(mocks.upsertAuthProfile).toHaveBeenCalledWith({
      profileId: "anthropic:default",
      credential: {
        type: "token",
        provider: "anthropic",
        token: `sk-ant-oat01-${"b".repeat(80)}`,
      },
      agentDir: "/tmp/lada/agents/main",
    });
  });
});


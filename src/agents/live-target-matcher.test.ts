import { beforeAll, describe, expect, it, vi } from "vitest";

type CreateLiveTargetMatcher = typeof import("./live-target-matcher.js").createLiveTargetMatcher;
let createLiveTargetMatcher: CreateLiveTargetMatcher;

beforeAll(async () => {
  vi.doUnmock("../plugins/providers.js");
  vi.doUnmock("../plugins/manifest-registry.js");
  vi.resetModules();
  ({ createLiveTargetMatcher } = await import("./live-target-matcher.js"));
});

describe("createLiveTargetMatcher", () => {
  const env = {
    LADA_DISABLE_PLUGIN_MANIFEST_CACHE: "1",
  } as NodeJS.ProcessEnv;

  it("matches Anthropic-owned models for the lada-cli provider filter", () => {
    const matcher = createLiveTargetMatcher({
      providerFilter: new Set(["lada-cli"]),
      modelFilter: null,
      env,
    });

    expect(matcher.matchesProvider("anthropic")).toBe(true);
    expect(matcher.matchesProvider("openai")).toBe(false);
  });

  it("matches Anthropic model refs for lada-cli explicit model filters", () => {
    const matcher = createLiveTargetMatcher({
      providerFilter: null,
      modelFilter: new Set(["lada-cli/lada-sonnet-4-6"]),
      env,
    });

    expect(matcher.matchesModel("anthropic", "lada-sonnet-4-6")).toBe(true);
    expect(matcher.matchesModel("anthropic", "lada-opus-4-6")).toBe(false);
  });

  it("keeps direct provider/model matches working", () => {
    const matcher = createLiveTargetMatcher({
      providerFilter: new Set(["openrouter"]),
      modelFilter: new Set(["openrouter/openai/gpt-5.4"]),
      env,
    });

    expect(matcher.matchesProvider("openrouter")).toBe(true);
    expect(matcher.matchesModel("openrouter", "openai/gpt-5.4")).toBe(true);
  });
});


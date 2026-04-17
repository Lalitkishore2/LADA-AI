import { describe, expect, it } from "vitest";
import type { LADAConfig } from "../config/config.js";
import { applyProviderAuthConfigPatch } from "./provider-auth-choice-helpers.js";

describe("applyProviderAuthConfigPatch", () => {
  it("replaces patched default model maps instead of recursively merging them", () => {
    const base = {
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
    const patch = {
      agents: {
        defaults: {
          models: {
            "lada-cli/lada-sonnet-4-6": { alias: "Sonnet" },
            "lada-cli/lada-opus-4-6": { alias: "Opus" },
            "openai/gpt-5.2": {},
          },
        },
      },
    };

    const next = applyProviderAuthConfigPatch(base, patch);

    expect(next.agents?.defaults?.models).toEqual(patch.agents.defaults.models);
    expect(next.agents?.defaults?.model).toEqual(base.agents?.defaults?.model);
  });

  it("keeps normal recursive merges for unrelated provider auth patch fields", () => {
    const base = {
      agents: {
        defaults: {
          contextPruning: {
            mode: "cache-ttl",
            ttl: "30m",
          },
        },
      },
    } satisfies LADAConfig;
    const patch = {
      agents: {
        defaults: {
          contextPruning: {
            ttl: "1h",
          },
        },
      },
    };

    const next = applyProviderAuthConfigPatch(base, patch);

    expect(next).toEqual({
      agents: {
        defaults: {
          contextPruning: {
            mode: "cache-ttl",
            ttl: "1h",
          },
        },
      },
    });
  });
});


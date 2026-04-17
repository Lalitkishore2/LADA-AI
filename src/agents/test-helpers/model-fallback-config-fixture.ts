import type { LADAConfig } from "../../config/config.js";

export function makeModelFallbackCfg(overrides: Partial<LADAConfig> = {}): LADAConfig {
  return {
    agents: {
      defaults: {
        model: {
          primary: "openai/gpt-4.1-mini",
          fallbacks: ["anthropic/lada-haiku-3-5"],
        },
      },
    },
    ...overrides,
  } as LADAConfig;
}


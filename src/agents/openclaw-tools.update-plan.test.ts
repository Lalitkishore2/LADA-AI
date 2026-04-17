import { describe, expect, it } from "vitest";
import type { LADAConfig } from "../config/config.js";
import "./test-helpers/fast-core-tools.js";
import { createLADATools } from "./lada-tools.js";

describe("lada-tools update_plan gating", () => {
  it("keeps update_plan disabled by default", () => {
    const tools = createLADATools({
      config: {} as LADAConfig,
    });

    expect(tools.map((tool) => tool.name)).not.toContain("update_plan");
  });

  it("registers update_plan when explicitly enabled", () => {
    const tools = createLADATools({
      config: {
        tools: {
          experimental: {
            planTool: true,
          },
        },
      } as LADAConfig,
    });

    const updatePlan = tools.find((tool) => tool.name === "update_plan");
    expect(updatePlan?.displaySummary).toBe("Track a short structured work plan.");
  });

  it("auto-enables update_plan for OpenAI-family providers", () => {
    const openaiTools = createLADATools({
      config: {} as LADAConfig,
      modelProvider: "openai",
    });
    const codexTools = createLADATools({
      config: {} as LADAConfig,
      modelProvider: "openai-codex",
    });
    const anthropicTools = createLADATools({
      config: {} as LADAConfig,
      modelProvider: "anthropic",
    });

    expect(openaiTools.map((tool) => tool.name)).toContain("update_plan");
    expect(codexTools.map((tool) => tool.name)).toContain("update_plan");
    expect(anthropicTools.map((tool) => tool.name)).not.toContain("update_plan");
  });
});


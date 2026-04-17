import { afterEach, describe, expect, it, vi } from "vitest";
import type { LADAConfig } from "../config/config.js";
import { createLADATools } from "./lada-tools.js";

const hoisted = vi.hoisted(() => ({
  createImageGenerateTool: vi.fn(),
}));

vi.mock("../plugins/tools.js", () => ({
  resolvePluginTools: () => [],
  copyPluginToolMeta: () => undefined,
  getPluginToolMeta: () => undefined,
}));

vi.mock("./tools/image-generate-tool.js", () => ({
  createImageGenerateTool: (...args: unknown[]) => hoisted.createImageGenerateTool(...args),
}));

function asConfig(value: unknown): LADAConfig {
  return value as LADAConfig;
}

describe("lada tools image generation registration", () => {
  afterEach(() => {
    hoisted.createImageGenerateTool.mockReset();
  });

  it("registers image_generate when image-generation config is present", () => {
    hoisted.createImageGenerateTool.mockReturnValue({
      name: "image_generate",
      description: "image fixture tool",
      parameters: {
        type: "object",
        properties: {},
      },
      async execute() {
        return {
          content: [{ type: "text", text: "ok" }],
        };
      },
    });

    const tools = createLADATools({
      config: asConfig({
        agents: {
          defaults: {
            imageGenerationModel: {
              primary: "openai/gpt-image-1",
            },
          },
        },
      }),
      agentDir: "/tmp/lada-agent-main",
    });

    expect(tools.map((tool) => tool.name)).toContain("image_generate");
  });

  it("registers image_generate when a compatible provider has env-backed auth", () => {
    hoisted.createImageGenerateTool.mockReturnValue({
      name: "image_generate",
      description: "image fixture tool",
      parameters: {
        type: "object",
        properties: {},
      },
      async execute() {
        return {
          content: [{ type: "text", text: "ok" }],
        };
      },
    });

    const tools = createLADATools({
      config: asConfig({}),
      agentDir: "/tmp/lada-agent-main",
    });

    expect(tools.map((tool) => tool.name)).toContain("image_generate");
  });

  it("omits image_generate when config is absent and no compatible provider auth exists", () => {
    hoisted.createImageGenerateTool.mockReturnValue(null);

    const tools = createLADATools({
      config: asConfig({}),
      agentDir: "/tmp/lada-agent-main",
    });

    expect(tools.map((tool) => tool.name)).not.toContain("image_generate");
  });
});


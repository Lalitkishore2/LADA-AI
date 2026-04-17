import { describe, expect, it } from "vitest";
import { selectQaRunnerModelOptions } from "./model-catalog.runtime.js";

describe("qa runner model catalog", () => {
  it("filters to available rows and prefers gpt-5.4 first", () => {
    expect(
      selectQaRunnerModelOptions([
        {
          key: "anthropic/lada-sonnet-4-5",
          name: "LADA Sonnet 4.5",
          input: "text",
          available: true,
          missing: false,
        },
        {
          key: "openai/gpt-5.4",
          name: "gpt-5.4",
          input: "text,image",
          available: true,
          missing: false,
        },
        {
          key: "openrouter/auto",
          name: "OpenRouter Auto",
          input: "text",
          available: false,
          missing: false,
        },
      ]).map((entry) => entry.key),
    ).toEqual(["openai/gpt-5.4", "anthropic/lada-sonnet-4-5"]);
  });
});


import { describe, expect, it } from "vitest";
import {
  resolveLegacyAuthChoiceAliasesForCli,
  formatDeprecatedNonInteractiveAuthChoiceError,
  normalizeLegacyOnboardAuthChoice,
  resolveDeprecatedAuthChoiceReplacement,
} from "./auth-choice-legacy.js";

describe("auth choice legacy aliases", () => {
  it("maps lada-cli to the new anthropic cli choice", () => {
    expect(normalizeLegacyOnboardAuthChoice("lada-cli")).toBe("anthropic-cli");
    expect(resolveDeprecatedAuthChoiceReplacement("lada-cli")).toEqual({
      normalized: "anthropic-cli",
      message: 'Auth choice "lada-cli" is deprecated; using Anthropic LADA CLI setup instead.',
    });
    expect(formatDeprecatedNonInteractiveAuthChoiceError("lada-cli")).toBe(
      'Auth choice "lada-cli" is deprecated.\nUse "--auth-choice anthropic-cli".',
    );
  });

  it("sources deprecated cli aliases from plugin manifests", () => {
    expect(resolveLegacyAuthChoiceAliasesForCli()).toEqual(["lada-cli", "codex-cli"]);
  });
});


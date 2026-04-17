import { describe, expect, it } from "vitest";
import {
  ensureLADAExecMarkerOnProcess,
  markLADAExecEnv,
  LADA_CLI_ENV_VALUE,
  LADA_CLI_ENV_VAR,
} from "./lada-exec-env.js";

describe("markLADAExecEnv", () => {
  it("returns a cloned env object with the exec marker set", () => {
    const env = { PATH: "/usr/bin", LADA_CLI: "0" };
    const marked = markLADAExecEnv(env);

    expect(marked).toEqual({
      PATH: "/usr/bin",
      LADA_CLI: LADA_CLI_ENV_VALUE,
    });
    expect(marked).not.toBe(env);
    expect(env.LADA_CLI).toBe("0");
  });
});

describe("ensureLADAExecMarkerOnProcess", () => {
  it.each([
    {
      name: "mutates and returns the provided process env",
      env: { PATH: "/usr/bin" } as NodeJS.ProcessEnv,
    },
    {
      name: "overwrites an existing marker on the provided process env",
      env: { PATH: "/usr/bin", [LADA_CLI_ENV_VAR]: "0" } as NodeJS.ProcessEnv,
    },
  ])("$name", ({ env }) => {
    expect(ensureLADAExecMarkerOnProcess(env)).toBe(env);
    expect(env[LADA_CLI_ENV_VAR]).toBe(LADA_CLI_ENV_VALUE);
  });

  it("defaults to mutating process.env when no env object is provided", () => {
    const previous = process.env[LADA_CLI_ENV_VAR];
    delete process.env[LADA_CLI_ENV_VAR];

    try {
      expect(ensureLADAExecMarkerOnProcess()).toBe(process.env);
      expect(process.env[LADA_CLI_ENV_VAR]).toBe(LADA_CLI_ENV_VALUE);
    } finally {
      if (previous === undefined) {
        delete process.env[LADA_CLI_ENV_VAR];
      } else {
        process.env[LADA_CLI_ENV_VAR] = previous;
      }
    }
  });
});


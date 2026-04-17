import path from "node:path";
import { describe, expect, it } from "vitest";
import { formatCliCommand } from "./command-format.js";
import { applyCliProfileEnv, parseCliProfileArgs } from "./profile.js";

describe("parseCliProfileArgs", () => {
  it("leaves gateway --dev for subcommands", () => {
    const res = parseCliProfileArgs([
      "node",
      "lada",
      "gateway",
      "--dev",
      "--allow-unconfigured",
    ]);
    if (!res.ok) {
      throw new Error(res.error);
    }
    expect(res.profile).toBeNull();
    expect(res.argv).toEqual(["node", "lada", "gateway", "--dev", "--allow-unconfigured"]);
  });

  it("leaves gateway --dev for subcommands after leading root options", () => {
    const res = parseCliProfileArgs([
      "node",
      "lada",
      "--no-color",
      "gateway",
      "--dev",
      "--allow-unconfigured",
    ]);
    if (!res.ok) {
      throw new Error(res.error);
    }
    expect(res.profile).toBeNull();
    expect(res.argv).toEqual([
      "node",
      "lada",
      "--no-color",
      "gateway",
      "--dev",
      "--allow-unconfigured",
    ]);
  });

  it("still accepts global --dev before subcommand", () => {
    const res = parseCliProfileArgs(["node", "lada", "--dev", "gateway"]);
    if (!res.ok) {
      throw new Error(res.error);
    }
    expect(res.profile).toBe("dev");
    expect(res.argv).toEqual(["node", "lada", "gateway"]);
  });

  it("parses --profile value and strips it", () => {
    const res = parseCliProfileArgs(["node", "lada", "--profile", "work", "status"]);
    if (!res.ok) {
      throw new Error(res.error);
    }
    expect(res.profile).toBe("work");
    expect(res.argv).toEqual(["node", "lada", "status"]);
  });

  it("parses interleaved --profile after the command token", () => {
    const res = parseCliProfileArgs(["node", "lada", "status", "--profile", "work", "--deep"]);
    if (!res.ok) {
      throw new Error(res.error);
    }
    expect(res.profile).toBe("work");
    expect(res.argv).toEqual(["node", "lada", "status", "--deep"]);
  });

  it("parses interleaved --dev after the command token", () => {
    const res = parseCliProfileArgs(["node", "lada", "status", "--dev"]);
    if (!res.ok) {
      throw new Error(res.error);
    }
    expect(res.profile).toBe("dev");
    expect(res.argv).toEqual(["node", "lada", "status"]);
  });

  it("rejects missing profile value", () => {
    const res = parseCliProfileArgs(["node", "lada", "--profile"]);
    expect(res.ok).toBe(false);
  });

  it.each([
    ["--dev first", ["node", "lada", "--dev", "--profile", "work", "status"]],
    ["--profile first", ["node", "lada", "--profile", "work", "--dev", "status"]],
    ["interleaved after command", ["node", "lada", "status", "--profile", "work", "--dev"]],
  ])("rejects combining --dev with --profile (%s)", (_name, argv) => {
    const res = parseCliProfileArgs(argv);
    expect(res.ok).toBe(false);
  });
});

describe("applyCliProfileEnv", () => {
  it("fills env defaults for dev profile", () => {
    const env: Record<string, string | undefined> = {};
    applyCliProfileEnv({
      profile: "dev",
      env,
      homedir: () => "/home/peter",
    });
    const expectedStateDir = path.join(path.resolve("/home/peter"), ".lada-dev");
    expect(env.LADA_PROFILE).toBe("dev");
    expect(env.LADA_STATE_DIR).toBe(expectedStateDir);
    expect(env.LADA_CONFIG_PATH).toBe(path.join(expectedStateDir, "lada.json"));
    expect(env.LADA_GATEWAY_PORT).toBe("19001");
  });

  it("does not override explicit env values", () => {
    const env: Record<string, string | undefined> = {
      LADA_STATE_DIR: "/custom",
      LADA_GATEWAY_PORT: "19099",
    };
    applyCliProfileEnv({
      profile: "dev",
      env,
      homedir: () => "/home/peter",
    });
    expect(env.LADA_STATE_DIR).toBe("/custom");
    expect(env.LADA_GATEWAY_PORT).toBe("19099");
    expect(env.LADA_CONFIG_PATH).toBe(path.join("/custom", "lada.json"));
  });

  it("uses LADA_HOME when deriving profile state dir", () => {
    const env: Record<string, string | undefined> = {
      LADA_HOME: "/srv/lada-home",
      HOME: "/home/other",
    };
    applyCliProfileEnv({
      profile: "work",
      env,
      homedir: () => "/home/fallback",
    });

    const resolvedHome = path.resolve("/srv/lada-home");
    expect(env.LADA_STATE_DIR).toBe(path.join(resolvedHome, ".lada-work"));
    expect(env.LADA_CONFIG_PATH).toBe(
      path.join(resolvedHome, ".lada-work", "lada.json"),
    );
  });
});

describe("formatCliCommand", () => {
  it.each([
    {
      name: "no profile is set",
      cmd: "lada doctor --fix",
      env: {},
      expected: "lada doctor --fix",
    },
    {
      name: "profile is default",
      cmd: "lada doctor --fix",
      env: { LADA_PROFILE: "default" },
      expected: "lada doctor --fix",
    },
    {
      name: "profile is Default (case-insensitive)",
      cmd: "lada doctor --fix",
      env: { LADA_PROFILE: "Default" },
      expected: "lada doctor --fix",
    },
    {
      name: "profile is invalid",
      cmd: "lada doctor --fix",
      env: { LADA_PROFILE: "bad profile" },
      expected: "lada doctor --fix",
    },
    {
      name: "--profile is already present",
      cmd: "lada --profile work doctor --fix",
      env: { LADA_PROFILE: "work" },
      expected: "lada --profile work doctor --fix",
    },
    {
      name: "--dev is already present",
      cmd: "lada --dev doctor",
      env: { LADA_PROFILE: "dev" },
      expected: "lada --dev doctor",
    },
  ])("returns command unchanged when $name", ({ cmd, env, expected }) => {
    expect(formatCliCommand(cmd, env)).toBe(expected);
  });

  it("inserts --profile flag when profile is set", () => {
    expect(formatCliCommand("lada doctor --fix", { LADA_PROFILE: "work" })).toBe(
      "lada --profile work doctor --fix",
    );
  });

  it("trims whitespace from profile", () => {
    expect(formatCliCommand("lada doctor --fix", { LADA_PROFILE: "  jblada  " })).toBe(
      "lada --profile jblada doctor --fix",
    );
  });

  it("handles command with no args after lada", () => {
    expect(formatCliCommand("lada", { LADA_PROFILE: "test" })).toBe(
      "lada --profile test",
    );
  });

  it("handles pnpm wrapper", () => {
    expect(formatCliCommand("pnpm lada doctor", { LADA_PROFILE: "work" })).toBe(
      "pnpm lada --profile work doctor",
    );
  });

  it("inserts --container when a container hint is set", () => {
    expect(
      formatCliCommand("lada gateway status --deep", { LADA_CONTAINER_HINT: "demo" }),
    ).toBe("lada --container demo gateway status --deep");
  });

  it("preserves both --container and --profile hints", () => {
    expect(
      formatCliCommand("lada doctor", {
        LADA_CONTAINER_HINT: "demo",
        LADA_PROFILE: "work",
      }),
    ).toBe("lada --container demo doctor");
  });

  it("does not prepend --container for update commands", () => {
    expect(formatCliCommand("lada update", { LADA_CONTAINER_HINT: "demo" })).toBe(
      "lada update",
    );
    expect(
      formatCliCommand("pnpm lada update --channel beta", { LADA_CONTAINER_HINT: "demo" }),
    ).toBe("pnpm lada update --channel beta");
  });
});


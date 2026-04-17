import fs from "node:fs";
import path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { importFreshModule } from "./helpers/import-fresh.js";
import { cleanupTempDirs, makeTempDir } from "./helpers/temp-dir.js";
import { installTestEnv } from "./test-env.js";

const ORIGINAL_ENV = { ...process.env };

const tempDirs = new Set<string>();
const cleanupFns: Array<() => void> = [];

function restoreProcessEnv(): void {
  for (const key of Object.keys(process.env)) {
    if (!(key in ORIGINAL_ENV)) {
      delete process.env[key];
    }
  }
  for (const [key, value] of Object.entries(ORIGINAL_ENV)) {
    if (value === undefined) {
      delete process.env[key];
    } else {
      process.env[key] = value;
    }
  }
}

function writeFile(targetPath: string, content: string): void {
  fs.mkdirSync(path.dirname(targetPath), { recursive: true });
  fs.writeFileSync(targetPath, content, "utf8");
}

function createTempHome(): string {
  return makeTempDir(tempDirs, "lada-test-env-real-home-");
}

afterEach(() => {
  while (cleanupFns.length > 0) {
    cleanupFns.pop()?.();
  }
  restoreProcessEnv();
  cleanupTempDirs(tempDirs);
});

describe("installTestEnv", () => {
  it("keeps live tests on a temp HOME while copying config and auth state", () => {
    const realHome = createTempHome();
    const priorIsolatedHome = createTempHome();
    writeFile(path.join(realHome, ".profile"), "export TEST_PROFILE_ONLY=from-profile\n");
    writeFile(
      path.join(realHome, "custom-lada.json5"),
      `{
        // Preserve provider config, strip host-bound paths.
        agents: {
          defaults: {
            workspace: "/Users/peter/Projects",
            agentDir: "/Users/peter/.lada/agents/main/agent",
          },
          list: [
            {
              id: "dev",
              workspace: "/Users/peter/dev-workspace",
              agentDir: "/Users/peter/.lada/agents/dev/agent",
            },
          ],
        },
        models: {
          providers: {
            custom: { baseUrl: "https://example.test/v1" },
          },
        },
        channels: {
          telegram: {
            streaming: {
              mode: "block",
              chunkMode: "newline",
              block: {
                enabled: true,
              },
              preview: {
                chunk: {
                  minChars: 120,
                },
              },
            },
          },
        },
      }`,
    );
    writeFile(path.join(realHome, ".lada", "credentials", "token.txt"), "secret\n");
    writeFile(
      path.join(realHome, ".lada", "agents", "main", "agent", "auth-profiles.json"),
      JSON.stringify({ version: 1, profiles: { default: { provider: "openai" } } }, null, 2),
    );
    writeFile(path.join(realHome, ".lada", ".credentials.json"), '{"accessToken":"token"}\n');

    process.env.HOME = realHome;
    process.env.USERPROFILE = realHome;
    process.env.LADA_LIVE_TEST = "1";
    process.env.LADA_LIVE_TEST_QUIET = "1";
    process.env.LADA_CONFIG_PATH = "~/custom-lada.json5";
    process.env.LADA_TEST_HOME = priorIsolatedHome;
    process.env.LADA_STATE_DIR = path.join(priorIsolatedHome, ".lada");

    const testEnv = installTestEnv();
    cleanupFns.push(testEnv.cleanup);

    expect(testEnv.tempHome).not.toBe(realHome);
    expect(process.env.HOME).toBe(testEnv.tempHome);
    expect(process.env.LADA_TEST_HOME).toBe(testEnv.tempHome);
    expect(process.env.TEST_PROFILE_ONLY).toBe("from-profile");

    const copiedConfigPath = path.join(testEnv.tempHome, ".lada", "lada.json");
    const copiedConfig = JSON.parse(fs.readFileSync(copiedConfigPath, "utf8")) as {
      agents?: {
        defaults?: Record<string, unknown>;
        list?: Array<Record<string, unknown>>;
      };
      models?: { providers?: Record<string, unknown> };
      channels?: {
        telegram?: {
          streaming?: {
            mode?: string;
            chunkMode?: string;
            block?: { enabled?: boolean };
            preview?: { chunk?: { minChars?: number } };
          };
        };
      };
    };
    expect(copiedConfig.models?.providers?.custom).toEqual({ baseUrl: "https://example.test/v1" });
    expect(copiedConfig.agents?.defaults?.workspace).toBeUndefined();
    expect(copiedConfig.agents?.defaults?.agentDir).toBeUndefined();
    expect(copiedConfig.agents?.list?.[0]?.workspace).toBeUndefined();
    expect(copiedConfig.agents?.list?.[0]?.agentDir).toBeUndefined();
    expect(copiedConfig.channels?.telegram?.streaming).toEqual({
      mode: "block",
      chunkMode: "newline",
      block: { enabled: true },
      preview: { chunk: { minChars: 120 } },
    });

    expect(
      fs.existsSync(path.join(testEnv.tempHome, ".lada", "credentials", "token.txt")),
    ).toBe(true);
    expect(
      fs.existsSync(
        path.join(testEnv.tempHome, ".lada", "agents", "main", "agent", "auth-profiles.json"),
      ),
    ).toBe(true);
    expect(fs.existsSync(path.join(testEnv.tempHome, ".lada", ".credentials.json"))).toBe(true);
  });

  it("allows explicit live runs against the real HOME", () => {
    const realHome = createTempHome();
    writeFile(path.join(realHome, ".profile"), "export TEST_PROFILE_ONLY=from-profile\n");

    process.env.HOME = realHome;
    process.env.USERPROFILE = realHome;
    process.env.LADA_LIVE_TEST = "1";
    process.env.LADA_LIVE_USE_REAL_HOME = "1";
    process.env.LADA_LIVE_TEST_QUIET = "1";

    const testEnv = installTestEnv();

    expect(testEnv.tempHome).toBe(realHome);
    expect(process.env.HOME).toBe(realHome);
    expect(process.env.TEST_PROFILE_ONLY).toBe("from-profile");
  });

  it("does not load ~/.profile for normal isolated test runs", () => {
    const realHome = createTempHome();
    writeFile(path.join(realHome, ".profile"), "export TEST_PROFILE_ONLY=from-profile\n");

    process.env.HOME = realHome;
    process.env.USERPROFILE = realHome;
    delete process.env.LIVE;
    delete process.env.LADA_LIVE_TEST;
    delete process.env.LADA_LIVE_GATEWAY;
    delete process.env.LADA_LIVE_USE_REAL_HOME;
    delete process.env.LADA_LIVE_TEST_QUIET;

    const testEnv = installTestEnv();
    cleanupFns.push(testEnv.cleanup);

    expect(testEnv.tempHome).not.toBe(realHome);
    expect(process.env.TEST_PROFILE_ONLY).toBeUndefined();
  });

  it("falls back to parsing ~/.profile when bash is unavailable", async () => {
    const realHome = createTempHome();
    writeFile(path.join(realHome, ".profile"), "export TEST_PROFILE_ONLY=from-profile\n");

    process.env.HOME = realHome;
    process.env.USERPROFILE = realHome;
    process.env.LADA_LIVE_TEST = "1";
    process.env.LADA_LIVE_USE_REAL_HOME = "1";
    process.env.LADA_LIVE_TEST_QUIET = "1";

    vi.doMock("node:child_process", () => ({
      execFileSync: () => {
        throw Object.assign(new Error("bash missing"), { code: "ENOENT" });
      },
    }));

    const { installTestEnv: installFreshTestEnv } = await importFreshModule<
      typeof import("./test-env.js")
    >(import.meta.url, "./test-env.js?scope=profile-fallback");

    const testEnv = installFreshTestEnv();

    expect(testEnv.tempHome).toBe(realHome);
    expect(process.env.TEST_PROFILE_ONLY).toBe("from-profile");
  });
});


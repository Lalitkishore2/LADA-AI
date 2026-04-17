import fs from "node:fs";
import path from "node:path";
import { describe, expect, it, vi } from "vitest";
import { withTempDir } from "./test-helpers/temp-dir.js";
import {
  ensureDir,
  resolveConfigDir,
  resolveHomeDir,
  resolveUserPath,
  shortenHomeInString,
  shortenHomePath,
  sleep,
} from "./utils.js";

describe("ensureDir", () => {
  it("creates nested directory", async () => {
    await withTempDir({ prefix: "lada-test-" }, async (tmp) => {
      const target = path.join(tmp, "nested", "dir");
      await ensureDir(target);
      expect(fs.existsSync(target)).toBe(true);
    });
  });
});

describe("sleep", () => {
  it("resolves after delay using fake timers", async () => {
    vi.useFakeTimers();
    const promise = sleep(1000);
    vi.advanceTimersByTime(1000);
    await expect(promise).resolves.toBeUndefined();
    vi.useRealTimers();
  });
});

describe("resolveConfigDir", () => {
  it("prefers ~/.lada when legacy dir is missing", async () => {
    await withTempDir({ prefix: "lada-config-dir-" }, async (root) => {
      const newDir = path.join(root, ".lada");
      await fs.promises.mkdir(newDir, { recursive: true });
      const resolved = resolveConfigDir({} as NodeJS.ProcessEnv, () => root);
      expect(resolved).toBe(newDir);
    });
  });

  it("expands LADA_STATE_DIR using the provided env", () => {
    const env = {
      HOME: "/tmp/lada-home",
      LADA_STATE_DIR: "~/state",
    } as NodeJS.ProcessEnv;

    expect(resolveConfigDir(env)).toBe(path.resolve("/tmp/lada-home", "state"));
  });

  it("falls back to the config file directory when only LADA_CONFIG_PATH is set", () => {
    const env = {
      HOME: "/tmp/lada-home",
      LADA_CONFIG_PATH: "~/profiles/dev/lada.json",
    } as NodeJS.ProcessEnv;

    expect(resolveConfigDir(env)).toBe(path.resolve("/tmp/lada-home", "profiles", "dev"));
  });
});

describe("resolveHomeDir", () => {
  it("prefers LADA_HOME over HOME", () => {
    vi.stubEnv("LADA_HOME", "/srv/lada-home");
    vi.stubEnv("HOME", "/home/other");

    expect(resolveHomeDir()).toBe(path.resolve("/srv/lada-home"));

    vi.unstubAllEnvs();
  });
});

describe("shortenHomePath", () => {
  it("uses $LADA_HOME prefix when LADA_HOME is set", () => {
    vi.stubEnv("LADA_HOME", "/srv/lada-home");
    vi.stubEnv("HOME", "/home/other");

    expect(shortenHomePath(`${path.resolve("/srv/lada-home")}/.lada/lada.json`)).toBe(
      "$LADA_HOME/.lada/lada.json",
    );

    vi.unstubAllEnvs();
  });
});

describe("shortenHomeInString", () => {
  it("uses $LADA_HOME replacement when LADA_HOME is set", () => {
    vi.stubEnv("LADA_HOME", "/srv/lada-home");
    vi.stubEnv("HOME", "/home/other");

    expect(
      shortenHomeInString(`config: ${path.resolve("/srv/lada-home")}/.lada/lada.json`),
    ).toBe("config: $LADA_HOME/.lada/lada.json");

    vi.unstubAllEnvs();
  });
});

describe("resolveUserPath", () => {
  it("expands ~ to home dir", () => {
    expect(resolveUserPath("~", {}, () => "/Users/thoffman")).toBe(path.resolve("/Users/thoffman"));
  });

  it("expands ~/ to home dir", () => {
    expect(resolveUserPath("~/lada", {}, () => "/Users/thoffman")).toBe(
      path.resolve("/Users/thoffman", "lada"),
    );
  });

  it("resolves relative paths", () => {
    expect(resolveUserPath("tmp/dir")).toBe(path.resolve("tmp/dir"));
  });

  it("prefers LADA_HOME for tilde expansion", () => {
    vi.stubEnv("LADA_HOME", "/srv/lada-home");
    vi.stubEnv("HOME", "/home/other");

    expect(resolveUserPath("~/lada")).toBe(path.resolve("/srv/lada-home", "lada"));

    vi.unstubAllEnvs();
  });

  it("uses the provided env for tilde expansion", () => {
    const env = {
      HOME: "/tmp/lada-home",
      LADA_HOME: "/srv/lada-home",
    } as NodeJS.ProcessEnv;

    expect(resolveUserPath("~/lada", env)).toBe(path.resolve("/srv/lada-home", "lada"));
  });

  it("keeps blank paths blank", () => {
    expect(resolveUserPath("")).toBe("");
    expect(resolveUserPath("   ")).toBe("");
  });

  it("returns empty string for undefined/null input", () => {
    expect(resolveUserPath(undefined as unknown as string)).toBe("");
    expect(resolveUserPath(null as unknown as string)).toBe("");
  });
});


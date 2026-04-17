import { afterEach, describe, expect, it, vi } from "vitest";
import { importFreshModule } from "../../test/helpers/import-fresh.js";

type LoggerModule = typeof import("./logger.js");

const originalGetBuiltinModule = (
  process as NodeJS.Process & { getBuiltinModule?: (id: string) => unknown }
).getBuiltinModule;

async function importBrowserSafeLogger(params?: {
  resolvePreferredLADATmpDir?: ReturnType<typeof vi.fn>;
}): Promise<{
  module: LoggerModule;
  resolvePreferredLADATmpDir: ReturnType<typeof vi.fn>;
}> {
  const resolvePreferredLADATmpDir =
    params?.resolvePreferredLADATmpDir ??
    vi.fn(() => {
      throw new Error("resolvePreferredLADATmpDir should not run during browser-safe import");
    });

  vi.doMock("../infra/tmp-lada-dir.js", async () => {
    const actual = await vi.importActual<typeof import("../infra/tmp-lada-dir.js")>(
      "../infra/tmp-lada-dir.js",
    );
    return {
      ...actual,
      resolvePreferredLADATmpDir,
    };
  });

  Object.defineProperty(process, "getBuiltinModule", {
    configurable: true,
    value: undefined,
  });

  const module = await importFreshModule<LoggerModule>(
    import.meta.url,
    "./logger.js?scope=browser-safe",
  );
  return { module, resolvePreferredLADATmpDir };
}

describe("logging/logger browser-safe import", () => {
  afterEach(() => {
    vi.doUnmock("../infra/tmp-lada-dir.js");
    Object.defineProperty(process, "getBuiltinModule", {
      configurable: true,
      value: originalGetBuiltinModule,
    });
  });

  it("does not resolve the preferred temp dir at import time when node fs is unavailable", async () => {
    const { module, resolvePreferredLADATmpDir } = await importBrowserSafeLogger();

    expect(resolvePreferredLADATmpDir).not.toHaveBeenCalled();
    expect(module.DEFAULT_LOG_DIR).toBe("/tmp/lada");
    expect(module.DEFAULT_LOG_FILE).toBe("/tmp/lada/lada.log");
  });

  it("disables file logging when imported in a browser-like environment", async () => {
    const { module, resolvePreferredLADATmpDir } = await importBrowserSafeLogger();

    expect(module.getResolvedLoggerSettings()).toMatchObject({
      level: "silent",
      file: "/tmp/lada/lada.log",
    });
    expect(module.isFileLogLevelEnabled("info")).toBe(false);
    expect(() => module.getLogger().info("browser-safe")).not.toThrow();
    expect(resolvePreferredLADATmpDir).not.toHaveBeenCalled();
  });
});


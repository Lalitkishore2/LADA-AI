import { beforeAll, describe, expect, it, vi } from "vitest";

const resolveGatewayLogPathsMock = vi.fn(() => ({
  stdoutPath: "C:\\tmp\\lada-state\\logs\\gateway.log",
  stderrPath: "C:\\tmp\\lada-state\\logs\\gateway.err.log",
}));

vi.mock("./launchd.js", () => ({
  resolveGatewayLogPaths: resolveGatewayLogPathsMock,
}));

let buildPlatformRuntimeLogHints: typeof import("./runtime-hints.js").buildPlatformRuntimeLogHints;

describe("buildPlatformRuntimeLogHints", () => {
  beforeAll(async () => {
    ({ buildPlatformRuntimeLogHints } = await import("./runtime-hints.js"));
  });

  it("strips windows drive prefixes from darwin display paths", () => {
    expect(
      buildPlatformRuntimeLogHints({
        platform: "darwin",
        systemdServiceName: "lada-gateway",
        windowsTaskName: "LADA Gateway",
      }),
    ).toEqual([
      "Launchd stdout (if installed): /tmp/lada-state/logs/gateway.log",
      "Launchd stderr (if installed): /tmp/lada-state/logs/gateway.err.log",
    ]);
  });
});


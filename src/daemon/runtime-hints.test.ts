import { describe, expect, it } from "vitest";
import { buildPlatformRuntimeLogHints, buildPlatformServiceStartHints } from "./runtime-hints.js";

describe("buildPlatformRuntimeLogHints", () => {
  it("renders launchd log hints on darwin", () => {
    expect(
      buildPlatformRuntimeLogHints({
        platform: "darwin",
        env: {
          LADA_STATE_DIR: "/tmp/lada-state",
          LADA_LOG_PREFIX: "gateway",
        },
        systemdServiceName: "lada-gateway",
        windowsTaskName: "LADA Gateway",
      }),
    ).toEqual([
      "Launchd stdout (if installed): /tmp/lada-state/logs/gateway.log",
      "Launchd stderr (if installed): /tmp/lada-state/logs/gateway.err.log",
    ]);
  });

  it("renders systemd and windows hints by platform", () => {
    expect(
      buildPlatformRuntimeLogHints({
        platform: "linux",
        systemdServiceName: "lada-gateway",
        windowsTaskName: "LADA Gateway",
      }),
    ).toEqual(["Logs: journalctl --user -u lada-gateway.service -n 200 --no-pager"]);
    expect(
      buildPlatformRuntimeLogHints({
        platform: "win32",
        systemdServiceName: "lada-gateway",
        windowsTaskName: "LADA Gateway",
      }),
    ).toEqual(['Logs: schtasks /Query /TN "LADA Gateway" /V /FO LIST']);
  });
});

describe("buildPlatformServiceStartHints", () => {
  it("builds platform-specific service start hints", () => {
    expect(
      buildPlatformServiceStartHints({
        platform: "darwin",
        installCommand: "lada gateway install",
        startCommand: "lada gateway",
        launchAgentPlistPath: "~/Library/LaunchAgents/com.lada.gateway.plist",
        systemdServiceName: "lada-gateway",
        windowsTaskName: "LADA Gateway",
      }),
    ).toEqual([
      "lada gateway install",
      "lada gateway",
      "launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.lada.gateway.plist",
    ]);
    expect(
      buildPlatformServiceStartHints({
        platform: "linux",
        installCommand: "lada gateway install",
        startCommand: "lada gateway",
        launchAgentPlistPath: "~/Library/LaunchAgents/com.lada.gateway.plist",
        systemdServiceName: "lada-gateway",
        windowsTaskName: "LADA Gateway",
      }),
    ).toEqual([
      "lada gateway install",
      "lada gateway",
      "systemctl --user start lada-gateway.service",
    ]);
  });
});


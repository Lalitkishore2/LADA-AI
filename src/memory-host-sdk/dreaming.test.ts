import { describe, expect, it, vi } from "vitest";
import type { LADAConfig } from "../config/config.js";

const resolveDefaultAgentId = vi.hoisted(() => vi.fn(() => "main"));
const resolveAgentWorkspaceDir = vi.hoisted(() =>
  vi.fn((_cfg: LADAConfig, agentId: string) => `/workspace/${agentId}`),
);

vi.mock("../agents/agent-scope.js", () => ({
  resolveDefaultAgentId,
  resolveAgentWorkspaceDir,
}));

import {
  formatMemoryDreamingDay,
  isSameMemoryDreamingDay,
  resolveMemoryDreamingPluginConfig,
  resolveMemoryDreamingPluginId,
  resolveMemoryDreamingConfig,
  resolveMemoryDreamingWorkspaces,
} from "./dreaming.js";

describe("memory dreaming host helpers", () => {
  it("normalizes string settings from the dreaming config", () => {
    const resolved = resolveMemoryDreamingConfig({
      pluginConfig: {
        dreaming: {
          enabled: true,
          frequency: "0 */4 * * *",
          timezone: "Europe/London",
          storage: {
            mode: "both",
            separateReports: true,
          },
          phases: {
            deep: {
              limit: "5",
              minScore: "0.9",
              minRecallCount: "4",
              minUniqueQueries: "2",
              recencyHalfLifeDays: "21",
              maxAgeDays: "30",
            },
          },
        },
      },
    });

    expect(resolved.enabled).toBe(true);
    expect(resolved.frequency).toBe("0 */4 * * *");
    expect(resolved.timezone).toBe("Europe/London");
    expect(resolved.storage).toEqual({
      mode: "both",
      separateReports: true,
    });
    expect(resolved.phases.deep).toMatchObject({
      cron: "0 */4 * * *",
      limit: 5,
      minScore: 0.9,
      minRecallCount: 4,
      minUniqueQueries: 2,
      recencyHalfLifeDays: 21,
      maxAgeDays: 30,
    });
  });

  it("falls back to cfg timezone and deep defaults", () => {
    const cfg = {
      agents: {
        defaults: {
          userTimezone: "America/Los_Angeles",
        },
      },
    } as LADAConfig;

    const resolved = resolveMemoryDreamingConfig({
      pluginConfig: {},
      cfg,
    });

    expect(resolved.enabled).toBe(false);
    expect(resolved.frequency).toBe("0 3 * * *");
    expect(resolved.timezone).toBe("America/Los_Angeles");
    expect(resolved.phases.deep).toMatchObject({
      cron: "0 3 * * *",
      limit: 10,
      minScore: 0.8,
      recencyHalfLifeDays: 14,
      maxAgeDays: 30,
    });
  });

  it("applies top-level dreaming frequency across all phases", () => {
    const resolved = resolveMemoryDreamingConfig({
      pluginConfig: {
        dreaming: {
          enabled: true,
          frequency: "15 */8 * * *",
        },
      },
    });

    expect(resolved.frequency).toBe("15 */8 * * *");
    expect(resolved.phases.light.cron).toBe("15 */8 * * *");
    expect(resolved.phases.deep.cron).toBe("15 */8 * * *");
    expect(resolved.phases.rem.cron).toBe("15 */8 * * *");
  });

  it("dedupes shared workspaces across all configured agents", () => {
    resolveAgentWorkspaceDir.mockImplementation((_cfg: LADAConfig, agentId: string) => {
      if (agentId === "alpha") {
        return "/workspace/shared";
      }
      if (agentId === "gamma") {
        return "/workspace/shared";
      }
      return `/workspace/${agentId}`;
    });

    const cfg = {
      agents: {
        list: [{ id: "alpha" }, { id: "beta" }, { id: "gamma" }],
      },
    } as LADAConfig;

    expect(resolveMemoryDreamingWorkspaces(cfg)).toEqual([
      {
        workspaceDir: "/workspace/shared",
        agentIds: ["alpha", "gamma"],
      },
      {
        workspaceDir: "/workspace/beta",
        agentIds: ["beta"],
      },
    ]);
  });

  it("uses default agent fallback and timezone-aware day helpers", () => {
    resolveDefaultAgentId.mockReturnValue("fallback");
    const cfg = {} as LADAConfig;

    expect(resolveMemoryDreamingWorkspaces(cfg)).toEqual([
      {
        workspaceDir: "/workspace/fallback",
        agentIds: ["fallback"],
      },
    ]);

    expect(
      formatMemoryDreamingDay(Date.parse("2026-04-02T06:30:00.000Z"), "America/Los_Angeles"),
    ).toBe("2026-04-01");
    expect(
      isSameMemoryDreamingDay(
        Date.parse("2026-04-02T06:30:00.000Z"),
        Date.parse("2026-04-02T06:50:00.000Z"),
        "America/Los_Angeles",
      ),
    ).toBe(true);
    expect(
      resolveMemoryDreamingPluginId({
        plugins: {
          slots: {
            memory: "memos-local-lada-plugin",
          },
        },
      } as LADAConfig),
    ).toBe("memos-local-lada-plugin");
    expect(
      resolveMemoryDreamingPluginConfig({
        plugins: {
          slots: {
            memory: "memos-local-lada-plugin",
          },
          entries: {
            "memos-local-lada-plugin": {
              config: {
                dreaming: {
                  enabled: true,
                },
              },
            },
          },
        },
      } as LADAConfig),
    ).toEqual({
      dreaming: {
        enabled: true,
      },
    });
    expect(
      resolveMemoryDreamingPluginConfig({
        plugins: {
          entries: {
            "memory-core": {
              config: {
                dreaming: {
                  enabled: true,
                },
              },
            },
          },
        },
      } as LADAConfig),
    ).toEqual({
      dreaming: {
        enabled: true,
      },
    });
  });

  it('falls back to memory-core when memory slot is "none" or blank', () => {
    expect(
      resolveMemoryDreamingPluginId({
        plugins: {
          slots: {
            memory: "none",
          },
        },
      } as LADAConfig),
    ).toBe("memory-core");

    expect(
      resolveMemoryDreamingPluginConfig({
        plugins: {
          slots: {
            memory: "   ",
          },
          entries: {
            "memory-core": {
              config: {
                dreaming: {
                  enabled: true,
                },
              },
            },
          },
        },
      } as LADAConfig),
    ).toEqual({
      dreaming: {
        enabled: true,
      },
    });
  });
});


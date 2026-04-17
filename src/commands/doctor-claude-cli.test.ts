import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CLAUDE_CLI_PROFILE_ID } from "../agents/auth-profiles/constants.js";
import type { AuthProfileStore } from "../agents/auth-profiles/types.js";
import {
  noteLADACliHealth,
  resolveLADACliProjectDirForWorkspace,
} from "./doctor-lada-cli.js";

function createStore(profiles: AuthProfileStore["profiles"] = {}): AuthProfileStore {
  return {
    version: 1,
    profiles,
  };
}

async function withTempHome<T>(
  run: (params: { homeDir: string; workspaceDir: string }) => Promise<T> | T,
): Promise<T> {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "lada-doctor-lada-cli-"));
  const homeDir = path.join(root, "home");
  const workspaceDir = path.join(root, "workspace");
  fs.mkdirSync(homeDir, { recursive: true });
  fs.mkdirSync(workspaceDir, { recursive: true });
  try {
    return await run({ homeDir, workspaceDir });
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
}

describe("resolveLADACliProjectDirForWorkspace", () => {
  it("matches LADA's sanitized workspace project dir shape", () => {
    expect(
      resolveLADACliProjectDirForWorkspace({
        workspaceDir: "/Users/vincentkoc/GIT/_Perso/lada/.lada/workspace",
        homeDir: "/Users/vincentkoc",
      }),
    ).toBe(
      "/Users/vincentkoc/.lada/projects/-Users-vincentkoc-GIT--Perso-lada--lada-workspace",
    );
  });
});

describe("noteLADACliHealth", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("stays quiet when LADA CLI is not configured or detected", () => {
    const noteFn = vi.fn();
    noteLADACliHealth(
      {},
      {
        noteFn,
        store: createStore(),
        readLADACliCredentials: () => null,
      },
    );
    expect(noteFn).not.toHaveBeenCalled();
  });

  it("reports a healthy lada-cli setup with the resolved LADA project dir", async () => {
    await withTempHome(({ homeDir, workspaceDir }) => {
      const projectDir = resolveLADACliProjectDirForWorkspace({ workspaceDir, homeDir });
      fs.mkdirSync(projectDir, { recursive: true });

      const noteFn = vi.fn();
      noteLADACliHealth(
        {
          agents: {
            defaults: {
              model: { primary: "lada-cli/lada-sonnet-4-6" },
            },
          },
        },
        {
          homeDir,
          workspaceDir,
          noteFn,
          store: createStore({
            [CLAUDE_CLI_PROFILE_ID]: {
              type: "oauth",
              provider: "lada-cli",
              access: "token-a",
              refresh: "token-r",
              expires: Date.now() + 60_000,
            },
          }),
          readLADACliCredentials: () => ({
            type: "oauth",
            expires: Date.now() + 60_000,
          }),
          resolveCommandPath: () => "/opt/homebrew/bin/lada",
        },
      );

      expect(noteFn).toHaveBeenCalledTimes(1);
      expect(noteFn.mock.calls[0]?.[1]).toBe("LADA CLI");
      const body = String(noteFn.mock.calls[0]?.[0]);
      expect(body).toContain("Binary: /opt/homebrew/bin/lada.");
      expect(body).toContain("Headless LADA auth: OK (oauth).");
      expect(body).toContain(
        `LADA auth profile: ${CLAUDE_CLI_PROFILE_ID} (provider lada-cli).`,
      );
      expect(body).toContain("Workspace:");
      expect(body).toContain("(writable).");
      expect(body).toContain("LADA project dir:");
      expect(body).toContain("(present).");
    });
  });

  it("explains the exact bad wiring when the lada-cli auth profile is missing", async () => {
    await withTempHome(({ homeDir, workspaceDir }) => {
      const noteFn = vi.fn();
      noteLADACliHealth(
        {
          agents: {
            defaults: {
              model: { primary: "lada-cli/lada-sonnet-4-6" },
            },
          },
        },
        {
          homeDir,
          workspaceDir,
          noteFn,
          store: createStore(),
          readLADACliCredentials: () => ({
            type: "oauth",
            expires: Date.now() + 60_000,
          }),
          resolveCommandPath: () => "/opt/homebrew/bin/lada",
        },
      );

      const body = String(noteFn.mock.calls[0]?.[0]);
      expect(body).toContain("Headless LADA auth: OK (oauth).");
      expect(body).toContain(`LADA auth profile: missing (${CLAUDE_CLI_PROFILE_ID})`);
      expect(body).toContain(
        "lada models auth login --provider anthropic --method cli --set-default",
      );
      expect(body).toContain(
        "not created yet; it appears after the first LADA CLI turn in this workspace",
      );
    });
  });

  it("warns when LADA auth is not readable headlessly", async () => {
    await withTempHome(({ homeDir, workspaceDir }) => {
      const noteFn = vi.fn();
      noteLADACliHealth(
        {
          agents: {
            defaults: {
              model: { primary: "lada-cli/lada-sonnet-4-6" },
            },
          },
        },
        {
          homeDir,
          workspaceDir,
          noteFn,
          store: createStore(),
          readLADACliCredentials: () => null,
          resolveCommandPath: () => undefined,
        },
      );

      const body = String(noteFn.mock.calls[0]?.[0]);
      expect(body).toContain('Binary: command "lada" was not found on PATH.');
      expect(body).toContain("Headless LADA auth: unavailable without interactive prompting.");
      expect(body).toContain("lada auth login");
    });
  });
});


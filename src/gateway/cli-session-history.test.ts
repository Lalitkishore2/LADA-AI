import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import {
  augmentChatHistoryWithCliSessionImports,
  mergeImportedChatHistoryMessages,
  readLADACliSessionMessages,
  resolveLADACliSessionFilePath,
} from "./cli-session-history.js";

const ORIGINAL_HOME = process.env.HOME;

function createLADAHistoryLines(sessionId: string) {
  return [
    JSON.stringify({
      type: "queue-operation",
      operation: "enqueue",
      timestamp: "2026-03-26T16:29:54.722Z",
      sessionId,
      content: "[Thu 2026-03-26 16:29 GMT] Reply with exactly: AGENT CLI OK.",
    }),
    JSON.stringify({
      type: "user",
      uuid: "user-1",
      timestamp: "2026-03-26T16:29:54.800Z",
      message: {
        role: "user",
        content:
          'Sender (untrusted metadata):\n```json\n{"label":"lada-control-ui"}\n```\n\n[Thu 2026-03-26 16:29 GMT] hi',
      },
    }),
    JSON.stringify({
      type: "assistant",
      uuid: "assistant-1",
      timestamp: "2026-03-26T16:29:55.500Z",
      message: {
        role: "assistant",
        model: "lada-sonnet-4-6",
        content: [{ type: "text", text: "hello from LADA" }],
        stop_reason: "end_turn",
        usage: {
          input_tokens: 11,
          output_tokens: 7,
          cache_read_input_tokens: 22,
        },
      },
    }),
    JSON.stringify({
      type: "assistant",
      uuid: "assistant-2",
      timestamp: "2026-03-26T16:29:56.000Z",
      message: {
        role: "assistant",
        model: "lada-sonnet-4-6",
        content: [
          {
            type: "tool_use",
            id: "toolu_123",
            name: "Bash",
            input: {
              command: "pwd",
            },
          },
        ],
        stop_reason: "tool_use",
      },
    }),
    JSON.stringify({
      type: "user",
      uuid: "user-2",
      timestamp: "2026-03-26T16:29:56.400Z",
      message: {
        role: "user",
        content: [
          {
            type: "tool_result",
            tool_use_id: "toolu_123",
            content: "/tmp/demo",
          },
        ],
      },
    }),
    JSON.stringify({
      type: "last-prompt",
      sessionId,
      lastPrompt: "ignored",
    }),
  ].join("\n");
}

async function withLADAProjectsDir<T>(
  run: (params: { homeDir: string; sessionId: string; filePath: string }) => Promise<T>,
): Promise<T> {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "lada-lada-history-"));
  const homeDir = path.join(root, "home");
  const sessionId = "5b8b202c-f6bb-4046-9475-d2f15fd07530";
  const projectsDir = path.join(homeDir, ".lada", "projects", "demo-workspace");
  const filePath = path.join(projectsDir, `${sessionId}.jsonl`);
  await fs.mkdir(projectsDir, { recursive: true });
  await fs.writeFile(filePath, createLADAHistoryLines(sessionId), "utf-8");
  process.env.HOME = homeDir;
  try {
    return await run({ homeDir, sessionId, filePath });
  } finally {
    if (ORIGINAL_HOME === undefined) {
      delete process.env.HOME;
    } else {
      process.env.HOME = ORIGINAL_HOME;
    }
    await fs.rm(root, { recursive: true, force: true });
  }
}

describe("cli session history", () => {
  afterEach(() => {
    if (ORIGINAL_HOME === undefined) {
      delete process.env.HOME;
    } else {
      process.env.HOME = ORIGINAL_HOME;
    }
  });

  it("reads lada-cli session messages from the LADA projects store", async () => {
    await withLADAProjectsDir(async ({ homeDir, sessionId, filePath }) => {
      expect(resolveLADACliSessionFilePath({ cliSessionId: sessionId, homeDir })).toBe(filePath);
      const messages = readLADACliSessionMessages({ cliSessionId: sessionId, homeDir });
      expect(messages).toHaveLength(3);
      expect(messages[0]).toMatchObject({
        role: "user",
        content: expect.stringContaining("[Thu 2026-03-26 16:29 GMT] hi"),
        __lada: {
          importedFrom: "lada-cli",
          externalId: "user-1",
          cliSessionId: sessionId,
        },
      });
      expect(messages[1]).toMatchObject({
        role: "assistant",
        provider: "lada-cli",
        model: "lada-sonnet-4-6",
        stopReason: "end_turn",
        usage: {
          input: 11,
          output: 7,
          cacheRead: 22,
        },
        __lada: {
          importedFrom: "lada-cli",
          externalId: "assistant-1",
          cliSessionId: sessionId,
        },
      });
      expect(messages[2]).toMatchObject({
        role: "assistant",
        content: [
          {
            type: "toolcall",
            id: "toolu_123",
            name: "Bash",
            arguments: {
              command: "pwd",
            },
          },
          {
            type: "tool_result",
            name: "Bash",
            content: "/tmp/demo",
            tool_use_id: "toolu_123",
          },
        ],
      });
    });
  });

  it("deduplicates imported messages against similar local transcript entries", () => {
    const localMessages = [
      {
        role: "user",
        content: "hi",
        timestamp: Date.parse("2026-03-26T16:29:54.900Z"),
      },
      {
        role: "assistant",
        content: [{ type: "text", text: "hello from LADA" }],
        timestamp: Date.parse("2026-03-26T16:29:55.700Z"),
      },
    ];
    const importedMessages = [
      {
        role: "user",
        content:
          'Sender (untrusted metadata):\n```json\n{"label":"lada-control-ui"}\n```\n\n[Thu 2026-03-26 16:29 GMT] hi',
        timestamp: Date.parse("2026-03-26T16:29:54.800Z"),
        __lada: {
          importedFrom: "lada-cli",
          externalId: "user-1",
          cliSessionId: "session-1",
        },
      },
      {
        role: "assistant",
        content: [{ type: "text", text: "hello from LADA" }],
        timestamp: Date.parse("2026-03-26T16:29:55.500Z"),
        __lada: {
          importedFrom: "lada-cli",
          externalId: "assistant-1",
          cliSessionId: "session-1",
        },
      },
      {
        role: "user",
        content: "[Thu 2026-03-26 16:31 GMT] follow-up",
        timestamp: Date.parse("2026-03-26T16:31:00.000Z"),
        __lada: {
          importedFrom: "lada-cli",
          externalId: "user-2",
          cliSessionId: "session-1",
        },
      },
    ];

    const merged = mergeImportedChatHistoryMessages({ localMessages, importedMessages });
    expect(merged).toHaveLength(3);
    expect(merged[2]).toMatchObject({
      role: "user",
      __lada: {
        importedFrom: "lada-cli",
        externalId: "user-2",
      },
    });
  });

  it("augments chat history when a session has a lada-cli binding", async () => {
    await withLADAProjectsDir(async ({ homeDir, sessionId }) => {
      const messages = augmentChatHistoryWithCliSessionImports({
        entry: {
          sessionId: "lada-session",
          updatedAt: Date.now(),
          cliSessionBindings: {
            "lada-cli": {
              sessionId,
            },
          },
        },
        provider: "lada-cli",
        localMessages: [],
        homeDir,
      });
      expect(messages).toHaveLength(3);
      expect(messages[0]).toMatchObject({
        role: "user",
        __lada: { cliSessionId: sessionId },
      });
    });
  });

  it("falls back to legacy cliSessionIds when bindings are absent", async () => {
    await withLADAProjectsDir(async ({ homeDir, sessionId }) => {
      const messages = augmentChatHistoryWithCliSessionImports({
        entry: {
          sessionId: "lada-session",
          updatedAt: Date.now(),
          cliSessionIds: {
            "lada-cli": sessionId,
          },
        },
        provider: "lada-cli",
        localMessages: [],
        homeDir,
      });
      expect(messages).toHaveLength(3);
      expect(messages[1]).toMatchObject({
        role: "assistant",
        __lada: { cliSessionId: sessionId },
      });
    });
  });

  it("falls back to legacy ladaCliSessionId when newer fields are absent", async () => {
    await withLADAProjectsDir(async ({ homeDir, sessionId }) => {
      const messages = augmentChatHistoryWithCliSessionImports({
        entry: {
          sessionId: "lada-session",
          updatedAt: Date.now(),
          ladaCliSessionId: sessionId,
        },
        provider: "lada-cli",
        localMessages: [],
        homeDir,
      });
      expect(messages).toHaveLength(3);
      expect(messages[0]).toMatchObject({
        role: "user",
        __lada: { cliSessionId: sessionId },
      });
    });
  });
});


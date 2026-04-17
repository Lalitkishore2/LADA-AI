import { describe, expect, it } from "vitest";
import { resolveIrcInboundTarget } from "./monitor.js";

describe("irc monitor inbound target", () => {
  it("keeps channel target for group messages", () => {
    expect(
      resolveIrcInboundTarget({
        target: "#lada",
        senderNick: "alice",
      }),
    ).toEqual({
      isGroup: true,
      target: "#lada",
      rawTarget: "#lada",
    });
  });

  it("maps DM target to sender nick and preserves raw target", () => {
    expect(
      resolveIrcInboundTarget({
        target: "lada-bot",
        senderNick: "alice",
      }),
    ).toEqual({
      isGroup: false,
      target: "alice",
      rawTarget: "lada-bot",
    });
  });

  it("falls back to raw target when sender nick is empty", () => {
    expect(
      resolveIrcInboundTarget({
        target: "lada-bot",
        senderNick: " ",
      }),
    ).toEqual({
      isGroup: false,
      target: "lada-bot",
      rawTarget: "lada-bot",
    });
  });
});


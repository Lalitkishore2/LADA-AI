import { resolveChannelGroupRequireMention } from "lada/plugin-sdk/channel-policy";
import type { LADAConfig } from "lada/plugin-sdk/core";

type GoogleChatGroupContext = {
  cfg: LADAConfig;
  accountId?: string | null;
  groupId?: string | null;
};

export function resolveGoogleChatGroupRequireMention(params: GoogleChatGroupContext): boolean {
  return resolveChannelGroupRequireMention({
    cfg: params.cfg,
    channel: "googlechat",
    groupId: params.groupId,
    accountId: params.accountId,
  });
}


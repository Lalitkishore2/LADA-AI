import { formatTrimmedAllowFromEntries } from "lada/plugin-sdk/channel-config-helpers";
import type { ChannelStatusIssue } from "lada/plugin-sdk/channel-contract";
import { PAIRING_APPROVED_MESSAGE } from "lada/plugin-sdk/channel-status";
import {
  DEFAULT_ACCOUNT_ID,
  getChatChannelMeta,
  type ChannelPlugin,
  type LADAConfig,
} from "lada/plugin-sdk/core";
import { resolveChannelMediaMaxBytes } from "lada/plugin-sdk/media-runtime";
import { collectStatusIssuesFromLastError } from "lada/plugin-sdk/status-helpers";
import {
  resolveIMessageConfigAllowFrom,
  resolveIMessageConfigDefaultTo,
} from "./config-accessors.js";
import { looksLikeIMessageTargetId, normalizeIMessageMessagingTarget } from "./normalize.js";
export { chunkTextForOutbound } from "lada/plugin-sdk/text-chunking";

export {
  collectStatusIssuesFromLastError,
  DEFAULT_ACCOUNT_ID,
  formatTrimmedAllowFromEntries,
  getChatChannelMeta,
  looksLikeIMessageTargetId,
  normalizeIMessageMessagingTarget,
  PAIRING_APPROVED_MESSAGE,
  resolveChannelMediaMaxBytes,
  resolveIMessageConfigAllowFrom,
  resolveIMessageConfigDefaultTo,
};

export type { ChannelPlugin, ChannelStatusIssue, LADAConfig };


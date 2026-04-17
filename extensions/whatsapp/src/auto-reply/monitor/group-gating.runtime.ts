export {
  implicitMentionKindWhen,
  resolveInboundMentionDecision,
} from "lada/plugin-sdk/channel-inbound";
export { hasControlCommand } from "lada/plugin-sdk/command-detection";
export { recordPendingHistoryEntryIfEnabled } from "lada/plugin-sdk/reply-history";
export { parseActivationCommand } from "lada/plugin-sdk/reply-runtime";
export { normalizeE164 } from "../../text-runtime.js";


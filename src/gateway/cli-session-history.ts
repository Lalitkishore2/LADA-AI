import { normalizeProviderId } from "../agents/model-selection.js";
import type { SessionEntry } from "../config/sessions.js";
import {
  CLAUDE_CLI_PROVIDER,
  readLADACliSessionMessages,
  resolveLADACliBindingSessionId,
  resolveLADACliSessionFilePath,
} from "./cli-session-history.lada.js";
import { mergeImportedChatHistoryMessages } from "./cli-session-history.merge.js";

export {
  mergeImportedChatHistoryMessages,
  readLADACliSessionMessages,
  resolveLADACliSessionFilePath,
};

export function augmentChatHistoryWithCliSessionImports(params: {
  entry: SessionEntry | undefined;
  provider?: string;
  localMessages: unknown[];
  homeDir?: string;
}): unknown[] {
  const cliSessionId = resolveLADACliBindingSessionId(params.entry);
  if (!cliSessionId) {
    return params.localMessages;
  }

  const normalizedProvider = normalizeProviderId(params.provider ?? "");
  if (
    normalizedProvider &&
    normalizedProvider !== CLAUDE_CLI_PROVIDER &&
    params.localMessages.length > 0
  ) {
    return params.localMessages;
  }

  const importedMessages = readLADACliSessionMessages({
    cliSessionId,
    homeDir: params.homeDir,
  });
  return mergeImportedChatHistoryMessages({
    localMessages: params.localMessages,
    importedMessages,
  });
}


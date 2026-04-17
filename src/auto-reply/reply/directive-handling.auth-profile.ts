import { ensureAuthProfileStore } from "../../agents/auth-profiles.js";
import type { LADAConfig } from "../../config/config.js";
import { normalizeOptionalString } from "../../shared/string-coerce.js";

export function resolveProfileOverride(params: {
  rawProfile?: string;
  provider: string;
  cfg: LADAConfig;
  agentDir?: string;
}): { profileId?: string; error?: string } {
  const raw = normalizeOptionalString(params.rawProfile);
  if (!raw) {
    return {};
  }
  const store = ensureAuthProfileStore(params.agentDir, {
    allowKeychainPrompt: false,
  });
  const profile = store.profiles[raw];
  if (!profile) {
    return { error: `Auth profile "${raw}" not found.` };
  }
  if (profile.provider !== params.provider) {
    return {
      error: `Auth profile "${raw}" is for ${profile.provider}, not ${params.provider}.`,
    };
  }
  return { profileId: raw };
}


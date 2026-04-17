import { readLADACliCredentialsCached } from "lada/plugin-sdk/provider-auth";

export function readLADACliCredentialsForSetup() {
  return readLADACliCredentialsCached();
}

export function readLADACliCredentialsForSetupNonInteractive() {
  return readLADACliCredentialsCached({ allowKeychainPrompt: false });
}

export function readLADACliCredentialsForRuntime() {
  return readLADACliCredentialsCached({ allowKeychainPrompt: false });
}


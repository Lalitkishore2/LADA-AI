export const LADA_CLI_ENV_VAR = "LADA_CLI";
export const LADA_CLI_ENV_VALUE = "1";

export function markLADAExecEnv<T extends Record<string, string | undefined>>(env: T): T {
  return {
    ...env,
    [LADA_CLI_ENV_VAR]: LADA_CLI_ENV_VALUE,
  };
}

export function ensureLADAExecMarkerOnProcess(
  env: NodeJS.ProcessEnv = process.env,
): NodeJS.ProcessEnv {
  env[LADA_CLI_ENV_VAR] = LADA_CLI_ENV_VALUE;
  return env;
}


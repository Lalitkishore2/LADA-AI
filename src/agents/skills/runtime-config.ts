import { getRuntimeConfigSnapshot, type LADAConfig } from "../../config/config.js";

export function resolveSkillRuntimeConfig(config?: LADAConfig): LADAConfig | undefined {
  return getRuntimeConfigSnapshot() ?? config;
}


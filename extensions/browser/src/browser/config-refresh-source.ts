import { createConfigIO, getRuntimeConfigSnapshot, type LADAConfig } from "../config/config.js";

export function loadBrowserConfigForRuntimeRefresh(): LADAConfig {
  return getRuntimeConfigSnapshot() ?? createConfigIO().loadConfig();
}


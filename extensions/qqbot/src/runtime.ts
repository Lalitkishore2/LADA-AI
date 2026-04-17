import type { PluginRuntime } from "lada/plugin-sdk/core";
import { createPluginRuntimeStore } from "lada/plugin-sdk/runtime-store";

const { setRuntime: setQQBotRuntime, getRuntime: getQQBotRuntime } =
  createPluginRuntimeStore<PluginRuntime>("QQBot runtime not initialized");
export { getQQBotRuntime, setQQBotRuntime };


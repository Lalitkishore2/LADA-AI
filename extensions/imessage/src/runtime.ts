import type { PluginRuntime } from "lada/plugin-sdk/core";
import { createPluginRuntimeStore } from "lada/plugin-sdk/runtime-store";

const { setRuntime: setIMessageRuntime, getRuntime: getIMessageRuntime } =
  createPluginRuntimeStore<PluginRuntime>("iMessage runtime not initialized");
export { getIMessageRuntime, setIMessageRuntime };


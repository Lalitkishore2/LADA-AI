import type { PluginRuntime } from "lada/plugin-sdk/plugin-runtime";
import { createPluginRuntimeStore } from "lada/plugin-sdk/runtime-store";

const { setRuntime: setTlonRuntime, getRuntime: getTlonRuntime } =
  createPluginRuntimeStore<PluginRuntime>("Tlon runtime not initialized");
export { getTlonRuntime, setTlonRuntime };


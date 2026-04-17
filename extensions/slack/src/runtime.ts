import type { PluginRuntime } from "lada/plugin-sdk/channel-core";
import { createPluginRuntimeStore } from "lada/plugin-sdk/runtime-store";

type SlackChannelRuntime = {
  handleSlackAction?: typeof import("./action-runtime.js").handleSlackAction;
};

export type SlackRuntime = PluginRuntime & {
  channel: PluginRuntime["channel"] & {
    slack?: SlackChannelRuntime;
  };
};

const {
  setRuntime: setSlackRuntime,
  clearRuntime: clearSlackRuntime,
  tryGetRuntime: getOptionalSlackRuntime,
  getRuntime: getSlackRuntime,
} = createPluginRuntimeStore<SlackRuntime>("Slack runtime not initialized");
export { clearSlackRuntime, getOptionalSlackRuntime, getSlackRuntime, setSlackRuntime };


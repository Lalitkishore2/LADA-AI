import { defineSetupPluginEntry } from "lada/plugin-sdk/core";
import { qaChannelPlugin } from "./src/channel.js";

export default defineSetupPluginEntry(qaChannelPlugin);


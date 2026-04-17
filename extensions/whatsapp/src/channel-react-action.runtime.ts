import { readStringParam } from "lada/plugin-sdk/channel-actions";
import type { LADAConfig } from "lada/plugin-sdk/config-runtime";

export { resolveReactionMessageId } from "lada/plugin-sdk/channel-actions";
export { handleWhatsAppAction } from "./action-runtime.js";
export { normalizeWhatsAppTarget } from "./normalize.js";
export { readStringParam, type LADAConfig };


// Manual facade. Keep loader boundary explicit.
type FacadeModule = typeof import("@lada/anthropic/api.js");
import { loadBundledPluginPublicSurfaceModuleSync } from "./facade-loader.js";

function loadFacadeModule(): FacadeModule {
  return loadBundledPluginPublicSurfaceModuleSync<FacadeModule>({
    dirName: "anthropic",
    artifactBasename: "api.js",
  });
}
export const CLAUDE_CLI_BACKEND_ID: FacadeModule["CLAUDE_CLI_BACKEND_ID"] =
  loadFacadeModule()["CLAUDE_CLI_BACKEND_ID"];
export const isLADACliProvider: FacadeModule["isLADACliProvider"] = ((...args) =>
  loadFacadeModule()["isLADACliProvider"](...args)) as FacadeModule["isLADACliProvider"];


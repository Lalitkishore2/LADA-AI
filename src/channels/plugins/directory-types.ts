import type { LADAConfig } from "../../config/types.js";

export type DirectoryConfigParams = {
  cfg: LADAConfig;
  accountId?: string | null;
  query?: string | null;
  limit?: number | null;
};


import { describe, expect, it } from "vitest";
import type { LADAConfig } from "../config/config.js";
import { isDefaultBrowserPluginEnabled } from "../plugin-enabled.js";

describe("isDefaultBrowserPluginEnabled", () => {
  it("defaults to enabled", () => {
    expect(isDefaultBrowserPluginEnabled({} as LADAConfig)).toBe(true);
  });

  it("respects explicit plugin disablement", () => {
    expect(
      isDefaultBrowserPluginEnabled({
        plugins: {
          entries: {
            browser: {
              enabled: false,
            },
          },
        },
      } as LADAConfig),
    ).toBe(false);
  });
});


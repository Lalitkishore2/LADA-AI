import { describe, expect, it } from "vitest";
import { isLADAManagedMatrixDevice, summarizeMatrixDeviceHealth } from "./device-health.js";

describe("matrix device health", () => {
  it("detects LADA-managed device names", () => {
    expect(isLADAManagedMatrixDevice("LADA Gateway")).toBe(true);
    expect(isLADAManagedMatrixDevice("LADA Debug")).toBe(true);
    expect(isLADAManagedMatrixDevice("Element iPhone")).toBe(false);
    expect(isLADAManagedMatrixDevice(null)).toBe(false);
  });

  it("summarizes stale LADA-managed devices separately from the current device", () => {
    const summary = summarizeMatrixDeviceHealth([
      {
        deviceId: "du314Zpw3A",
        displayName: "LADA Gateway",
        current: true,
      },
      {
        deviceId: "BritdXC6iL",
        displayName: "LADA Gateway",
        current: false,
      },
      {
        deviceId: "G6NJU9cTgs",
        displayName: "LADA Debug",
        current: false,
      },
      {
        deviceId: "phone123",
        displayName: "Element iPhone",
        current: false,
      },
    ]);

    expect(summary.currentDeviceId).toBe("du314Zpw3A");
    expect(summary.currentLADADevices).toEqual([
      expect.objectContaining({ deviceId: "du314Zpw3A" }),
    ]);
    expect(summary.staleLADADevices).toEqual([
      expect.objectContaining({ deviceId: "BritdXC6iL" }),
      expect.objectContaining({ deviceId: "G6NJU9cTgs" }),
    ]);
  });
});


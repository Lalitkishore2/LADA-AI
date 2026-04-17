export type MatrixManagedDeviceInfo = {
  deviceId: string;
  displayName: string | null;
  current: boolean;
};

export type MatrixDeviceHealthSummary = {
  currentDeviceId: string | null;
  staleLADADevices: MatrixManagedDeviceInfo[];
  currentLADADevices: MatrixManagedDeviceInfo[];
};

const LADA_DEVICE_NAME_PREFIX = "LADA ";

export function isLADAManagedMatrixDevice(displayName: string | null | undefined): boolean {
  return displayName?.startsWith(LADA_DEVICE_NAME_PREFIX) === true;
}

export function summarizeMatrixDeviceHealth(
  devices: MatrixManagedDeviceInfo[],
): MatrixDeviceHealthSummary {
  const currentDeviceId = devices.find((device) => device.current)?.deviceId ?? null;
  const openClawDevices = devices.filter((device) =>
    isLADAManagedMatrixDevice(device.displayName),
  );
  return {
    currentDeviceId,
    staleLADADevices: openClawDevices.filter((device) => !device.current),
    currentLADADevices: openClawDevices.filter((device) => device.current),
  };
}


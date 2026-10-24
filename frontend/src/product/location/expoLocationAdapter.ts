/** GF-P0-115: Expo SDK 54 (expo-location ~19) foreground location adapter.
 *
 * Bridges the expo-location module onto the existing
 * `ForegroundNativeAdapter` contract in `frontierLiveGPS.ts`. Foreground only:
 * never requests background permission, never starts a background task, and
 * never stores, logs or uploads coordinates. The module is injected so tests
 * (and web builds) never touch the native binary.
 */
import type { ForegroundNativeAdapter, FrontierPositionFix } from "../frontierLiveGPS";

/** The subset of expo-location this adapter relies on. */
export type ExpoLocationModule = Readonly<{
  Accuracy: Readonly<{ High: number; BestForNavigation?: number }>;
  hasServicesEnabledAsync: () => Promise<boolean>;
  getForegroundPermissionsAsync: () => Promise<ExpoPermissionResponse>;
  requestForegroundPermissionsAsync: () => Promise<ExpoPermissionResponse>;
  watchPositionAsync: (
    options: Readonly<{ accuracy: number; timeInterval?: number; distanceInterval?: number; mayShowUserSettingsDialog?: boolean }>,
    callback: (location: ExpoLocationObject) => void,
    errorHandler?: (reason: string) => void,
  ) => Promise<{ remove: () => void }>;
}>;

export type ExpoPermissionResponse = Readonly<{
  status: "granted" | "denied" | "undetermined" | string;
  granted: boolean;
  canAskAgain: boolean;
}>;

export type ExpoLocationObject = Readonly<{
  coords: Readonly<{
    latitude: number;
    longitude: number;
    altitude: number | null;
    accuracy: number | null;
    altitudeAccuracy: number | null;
  }>;
  timestamp: number;
  mocked?: boolean;
}>;

export type LocationErrorCode =
  | "PERMISSION_DENIED"
  | "PERMISSION_BLOCKED"
  | "SERVICES_DISABLED"
  | "MOCKED_LOCATION"
  | "UNAVAILABLE"
  | "WATCH_FAILED";

export class FrontierLocationError extends Error {
  readonly code: LocationErrorCode;
  constructor(code: LocationErrorCode, message: string) {
    super(message);
    this.name = "FrontierLocationError";
    this.code = code;
  }
}

export type ExpoAdapterOptions = Readonly<{
  timeIntervalMs?: number;
  distanceIntervalM?: number;
  /** Reject OS-flagged mock locations (Android). Default true. */
  rejectMocked?: boolean;
}>;

export function toFrontierFix(location: ExpoLocationObject): FrontierPositionFix {
  const c = location.coords;
  return {
    latitude_deg: c.latitude,
    longitude_deg: c.longitude,
    altitude_m: typeof c.altitude === "number" ? c.altitude : null,
    // null accuracy is mapped to NaN so frontierLiveGPS validation rejects it.
    horizontal_accuracy_m: typeof c.accuracy === "number" ? c.accuracy : Number.NaN,
    vertical_accuracy_m: typeof c.altitudeAccuracy === "number" ? c.altitudeAccuracy : null,
    timestamp_ms: location.timestamp,
    sequence: 0,
    source: "host_os_gnss",
  };
}

/** Last permission outcome observed by an adapter (for UI denied states). */
export type PermissionOutcome = "unknown" | "granted" | "denied" | "blocked";

export type ExpoForegroundAdapter = ForegroundNativeAdapter & Readonly<{
  lastPermission: () => PermissionOutcome;
  checkPermission: () => Promise<PermissionOutcome>;
}>;

export function createExpoLocationAdapter(
  Location: ExpoLocationModule,
  options: ExpoAdapterOptions = {},
): ExpoForegroundAdapter {
  const timeInterval = options.timeIntervalMs ?? 1000;
  const distanceInterval = options.distanceIntervalM ?? 0;
  const rejectMocked = options.rejectMocked ?? true;
  if (!Number.isInteger(timeInterval) || timeInterval < 100 || timeInterval > 60000 ||
      !Number.isFinite(distanceInterval) || distanceInterval < 0 || distanceInterval > 1000) {
    throw new FrontierLocationError("UNAVAILABLE", "Invalid foreground location sampling policy");
  }
  let last: PermissionOutcome = "unknown";
  const classify = (r: ExpoPermissionResponse): PermissionOutcome =>
    r.granted || r.status === "granted" ? "granted" : r.canAskAgain ? "denied" : "blocked";

  return {
    lastPermission: () => last,
    async checkPermission() {
      last = classify(await Location.getForegroundPermissionsAsync());
      return last;
    },
    async requestForegroundPermission() {
      const current = classify(await Location.getForegroundPermissionsAsync());
      if (current === "granted") {
        last = current;
        return true;
      }
      if (current === "blocked") {
        last = current;
        return false;
      }
      last = classify(await Location.requestForegroundPermissionsAsync());
      return last === "granted";
    },
    async watchPosition(onFix, onError) {
      if (!(await Location.hasServicesEnabledAsync())) {
        throw new FrontierLocationError("SERVICES_DISABLED", "Device location services are turned off");
      }
      try {
        return await Location.watchPositionAsync(
          { accuracy: Location.Accuracy.High, timeInterval, distanceInterval, mayShowUserSettingsDialog: true },
          location => {
            if (rejectMocked && location.mocked === true) {
              onError(new FrontierLocationError("MOCKED_LOCATION", "Rejected OS-flagged mock location"));
              return;
            }
            onFix(toFrontierFix(location));
          },
          reason => onError(new FrontierLocationError("WATCH_FAILED", "Foreground location error: " + String(reason))),
        );
      } catch (err) {
        throw new FrontierLocationError(
          "WATCH_FAILED",
          "Could not start foreground location: " + (err instanceof Error ? err.message : String(err)),
        );
      }
    },
  };
}

/** Loads the installed expo-location native module, or null when absent (web/tests). */
export function loadExpoLocation(): ExpoLocationModule | null {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    return require("expo-location") as ExpoLocationModule;
  } catch {
    return null;
  }
}

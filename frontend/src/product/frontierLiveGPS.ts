/** Foreground-only device GPS bridge for the existing Expo/web shell.
 *
 * The browser uses its real Geolocation API (no mocked coordinates). Native
 * callers may supply an approved Expo Location adapter from a native host
 * build. No automatic startup, background task, storage, analytics, logs or
 * network upload. All permission prompts originate from a user interaction.
 */

export type FrontierPositionFix = Readonly<{
  latitude_deg: number;
  longitude_deg: number;
  altitude_m: number | null;
  horizontal_accuracy_m: number;
  vertical_accuracy_m: number | null;
  timestamp_ms: number;
  sequence: number;
  source: "host_os_gnss";
}>;

export type FrontierGPSSession = Readonly<{
  stop: () => void;
  active: () => boolean;
}>;

export type ForegroundNativeAdapter = Readonly<{
  requestForegroundPermission: () => Promise<boolean>;
  watchPosition: (
    onFix: (fix: FrontierPositionFix) => void,
    onError: (error: Error) => void,
  ) => Promise<{ remove: () => void }>;
}>;

export type GPSOptions = Readonly<{
  userInitiated: true;
  onFix: (fix: FrontierPositionFix) => void;
  onError: (error: Error) => void;
  native?: ForegroundNativeAdapter;
  maxAccuracyM?: number;
  maxAgeMs?: number;
}>;

function finite(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function validateFix(fix: FrontierPositionFix, maxAccuracyM: number, maxAgeMs: number): void {
  if (!finite(fix.latitude_deg) || Math.abs(fix.latitude_deg) > 90 ||
      !finite(fix.longitude_deg) || Math.abs(fix.longitude_deg) > 180 ||
      !finite(fix.horizontal_accuracy_m) || fix.horizontal_accuracy_m <= 0 ||
      fix.horizontal_accuracy_m > maxAccuracyM ||
      !finite(fix.timestamp_ms) || fix.timestamp_ms > Date.now() + 5000 ||
      Date.now() - fix.timestamp_ms > maxAgeMs) {
    throw new Error("Rejected stale, inaccurate, or invalid GPS observation");
  }
}

/** Call only from a foreground user gesture. Shutdown on visibility loss.
 *
 * For native Expo/Android/iOS, inject an explicitly installed
 * expo-location@SDK54-compatible provider. This module does not silently
 * add a native binary dependency or assume a background permission.
 */
export async function startForegroundGPS(options: GPSOptions): Promise<FrontierGPSSession> {
  if (options.userInitiated !== true) {
    throw new Error("Live GPS requires an explicit user action");
  }
  const maxAccuracyM = options.maxAccuracyM ?? 75;
  const maxAgeMs = options.maxAgeMs ?? 10000;
  if (!finite(maxAccuracyM) || maxAccuracyM <= 0 || maxAccuracyM > 1000 ||
      !Number.isInteger(maxAgeMs) || maxAgeMs < 100 || maxAgeMs > 60000) {
    throw new Error("Invalid GPS session quality policy");
  }
  let alive = true;
  let seq = 0;
  let stopImpl = () => {};
  let lastTimestamp = -1;
  const ingest = (reading: FrontierPositionFix): void => {
    if (!alive) return;
    try {
      validateFix(reading, maxAccuracyM, maxAgeMs);
      if (reading.timestamp_ms <= lastTimestamp) {
        throw new Error("GPS sequence or timestamp replay");
      }
      lastTimestamp = reading.timestamp_ms;
      options.onFix({ ...reading, sequence: ++seq });
    } catch (err) {
      options.onError(err instanceof Error ? err : new Error(String(err)));
    }
  };
  const stop = (): void => {
    if (!alive) return;
    alive = false;
    stopImpl();
  };
  const isWeb = typeof window !== "undefined" &&
                typeof navigator !== "undefined" &&
                typeof navigator.geolocation !== "undefined";
  if (isWeb && !options.native) {
    if (typeof document !== "undefined" && document.visibilityState === "hidden") {
      throw new Error("GPS is available only while the app is visible");
    }
    const watcher = navigator.geolocation.watchPosition(
      position => {
        if (typeof document !== "undefined" && document.visibilityState === "hidden") {
          stop();
          return;
        }
        ingest({
          latitude_deg: position.coords.latitude,
          longitude_deg: position.coords.longitude,
          altitude_m: position.coords.altitude,
          horizontal_accuracy_m: position.coords.accuracy,
          vertical_accuracy_m: position.coords.altitudeAccuracy,
          timestamp_ms: position.timestamp,
          sequence: 0,
          source: "host_os_gnss",
        });
      },
      error => options.onError(new Error("Foreground location unavailable: " + error.code)),
      { enableHighAccuracy: true, maximumAge: 0, timeout: 10000 },
    );
    const visibility = (): void => {
      if (document.visibilityState !== "visible") stop();
    };
    document.addEventListener("visibilitychange", visibility);
    stopImpl = () => {
      navigator.geolocation.clearWatch(watcher);
      document.removeEventListener("visibilitychange", visibility);
    };
  } else if (options.native) {
    const granted = await options.native.requestForegroundPermission();
    if (!granted) throw new Error("Foreground GPS permission denied");
    const subscription = await options.native.watchPosition(ingest, options.onError);
    stopImpl = () => subscription.remove();
  } else {
    throw new Error("Native foreground GPS adapter unavailable; no location access attempted");
  }
  return { stop, active: () => alive };
}

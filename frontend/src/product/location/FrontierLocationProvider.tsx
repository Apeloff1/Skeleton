/** GF-P0-115: React provider + hook for Frontier foreground location.
 *
 * State machine: idle -> requesting -> watching | denied | blocked | error.
 * `start()` must be called from a user gesture; the provider never starts on
 * mount. Going to background (AppState != active) stops the watch, so the
 * app never holds location while not visible. On-device acquisition and
 * revocation still need hardware verification (TODO.md GF-P0-115).
 */
import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { AppState, Platform } from "react-native";
import { startForegroundGPS, type ForegroundNativeAdapter, type FrontierGPSSession, type FrontierPositionFix } from "../frontierLiveGPS";
import { createExpoLocationAdapter, FrontierLocationError, loadExpoLocation, type ExpoAdapterOptions, type LocationErrorCode } from "./expoLocationAdapter";

export type FrontierLocationStatus = "idle" | "requesting" | "watching" | "denied" | "blocked" | "error" | "unavailable";

export type FrontierLocationState = Readonly<{
  status: FrontierLocationStatus;
  fix: FrontierPositionFix | null;
  error: Readonly<{ code: LocationErrorCode | "INVALID_FIX"; message: string }> | null;
}>;

export type FrontierLocationApi = FrontierLocationState & Readonly<{
  start: () => Promise<void>;
  stop: () => void;
}>;

const INITIAL: FrontierLocationState = { status: "idle", fix: null, error: null };
const Ctx = createContext<FrontierLocationApi | null>(null);

export type FrontierLocationProviderProps = Readonly<{
  children?: React.ReactNode;
  /** Inject an adapter (tests, custom hosts). Defaults to expo-location on native. */
  adapter?: ForegroundNativeAdapter | null;
  adapterOptions?: ExpoAdapterOptions;
  maxAccuracyM?: number;
  maxAgeMs?: number;
}>;

function defaultAdapter(options?: ExpoAdapterOptions): ForegroundNativeAdapter | null {
  if (Platform.OS === "web") return null; // web uses navigator.geolocation in frontierLiveGPS
  const mod = loadExpoLocation();
  return mod ? createExpoLocationAdapter(mod, options) : null;
}

export function FrontierLocationProvider(props: FrontierLocationProviderProps): React.ReactElement {
  const { children, adapter, adapterOptions, maxAccuracyM, maxAgeMs } = props;
  const [state, setState] = useState<FrontierLocationState>(INITIAL);
  const session = useRef<FrontierGPSSession | null>(null);
  const generation = useRef(0);
  const pendingStart = useRef<number | null>(null);
  const native = useMemo(
    () => (adapter !== undefined ? adapter : defaultAdapter(adapterOptions)),
    [adapter, adapterOptions],
  );

  const stop = useCallback(() => {
    generation.current += 1;
    session.current?.stop();
    session.current = null;
    // Backgrounding, revocation and explicit Stop must not retain an OS fix.
    setState({ status: "idle", fix: null, error: null });
  }, []);

  const start = useCallback(async () => {
    if (session.current?.active() || pendingStart.current === generation.current) return;
    const gen = ++generation.current;
    pendingStart.current = gen;
    if (Platform.OS !== "web" && !native) {
      pendingStart.current = null;
      setState({ status: "unavailable", fix: null, error: { code: "UNAVAILABLE", message: "expo-location is not installed in this build" } });
      return;
    }
    setState(s => ({ ...s, status: "requesting", error: null }));
    try {
      const s = await startForegroundGPS({
        userInitiated: true,
        native: native ?? undefined,
        maxAccuracyM,
        maxAgeMs,
        onFix: fix => {
          if (gen !== generation.current) return;
          setState({ status: "watching", fix, error: null });
        },
        onError: err => {
          if (gen !== generation.current) return;
          const code = err instanceof FrontierLocationError ? err.code : "INVALID_FIX";
          // Rejected fixes keep the watch alive; watch failures end it.
          if (code === "WATCH_FAILED") {
            session.current?.stop();
            session.current = null;
            setState({ status: "error", fix: null, error: { code, message: err.message } });
          } else {
            setState(st => ({ ...st, error: { code, message: err.message } }));
          }
        },
      });
      if (gen !== generation.current) {
        s.stop();
        return;
      }
      session.current = s;
      setState(st => (st.status === "requesting" ? { ...st, status: "watching" } : st));
    } catch (err) {
      if (gen !== generation.current) return;
      const message = err instanceof Error ? err.message : String(err);
      const blocked = native && "lastPermission" in native &&
        (native as { lastPermission: () => string }).lastPermission() === "blocked";
      if (/permission denied/i.test(message)) {
        setState({ status: blocked ? "blocked" : "denied", fix: null,
          error: { code: blocked ? "PERMISSION_BLOCKED" : "PERMISSION_DENIED", message } });
      } else {
        const code = err instanceof FrontierLocationError ? err.code : "UNAVAILABLE";
        setState({ status: "error", fix: null, error: { code, message } });
      }
    } finally {
      if (pendingStart.current === gen) pendingStart.current = null;
    }
  }, [native, maxAccuracyM, maxAgeMs]);

  useEffect(() => {
    const sub = AppState.addEventListener("change", next => {
      if (next !== "active") stop();
    });
    return () => {
      sub.remove();
      generation.current += 1;
      session.current?.stop();
      session.current = null;
    };
  }, [stop]);

  const api = useMemo<FrontierLocationApi>(() => ({ ...state, start, stop }), [state, start, stop]);
  return <Ctx.Provider value={api}>{children}</Ctx.Provider>;
}

export function useFrontierLocation(): FrontierLocationApi {
  const api = useContext(Ctx);
  if (!api) throw new Error("useFrontierLocation must be used inside <FrontierLocationProvider>");
  return api;
}

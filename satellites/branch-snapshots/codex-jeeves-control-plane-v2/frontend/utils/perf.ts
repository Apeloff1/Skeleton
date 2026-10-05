/**
 * perf — performance wraps for screens and hot paths.
 *
 * Bundle of small helpers that pair with withScreenGuard / safeTimers
 * to keep the app smooth on physical Android hardware.
 *
 *   • `useRenderTrace(name)` — measures mount-to-first-effect latency
 *     and reports anything slower than 300 ms to telemetry. Helpful
 *     for spotting accidentally-heavy screens.
 *
 *   • `useDebounced(value, ms)` — classic debounce hook.
 *
 *   • `useThrottled(value, ms)` — classic throttle hook (leading edge).
 *
 *   • `useStableCallback(fn)` — wraps a function in a ref so children
 *     can depend on it without triggering re-renders on every parent
 *     render (useful when handing a callback to FlatList renderItem).
 *
 *   • `useDeferredHeavy(fn, deps)` — runs an expensive computation in
 *     a requestAnimationFrame so it never blocks the first paint.
 *
 *   • `memoCache<T>(ttlMs)` — tiny TTL cache for prop derivations or
 *     network responses ("the same query within 5s returns cached").
 */
import { useEffect, useRef, useState, useCallback } from 'react';
import { InteractionManager } from 'react-native';
import { recordEvent } from './modalLogger';
import { traceStep } from './bootTracer';
import { getFeatureFlag } from './featureFlags';

const SLOW_RENDER_MS = 300;

// ── In-memory perf log so /perf can show recent renders ─────────────
export interface PerfSample { name: string; ms: number; ts: number; slow: boolean; }
const _perfLog: PerfSample[] = [];
const PERF_LOG_MAX = 200;
const _perfListeners = new Set<(log: PerfSample[]) => void>();

// Lazy AsyncStorage persistence — restore once at module load + flush
// debounced on every change. Wrapped in try/catch so failures never
// break the live perf flow.
let _perfRestored = false;
let _perfFlushT: any = null;
const PERF_STORAGE_KEY = '@perf/log:v1';

async function _restorePerf(): Promise<void> {
  if (_perfRestored) return;
  _perfRestored = true;
  try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const AsyncStorage = require('@react-native-async-storage/async-storage').default;
    const raw = await AsyncStorage.getItem(PERF_STORAGE_KEY);
    if (raw) {
      const arr = JSON.parse(raw) as PerfSample[];
      if (Array.isArray(arr)) {
        for (const s of arr.slice(-PERF_LOG_MAX)) _perfLog.push(s);
        // Notify any /perf screen already mounted so it refreshes
        // without needing the user to navigate away and back.
        _perfListeners.forEach(l => { try { l(_perfLog.slice()); } catch { /* swallow */ } });
      }
    }
  } catch { /* swallow */ }
}
// Kick off the restore right away (non-blocking).
_restorePerf();

function _schedulePerfFlush() {
  if (_perfFlushT) clearTimeout(_perfFlushT);
  _perfFlushT = setTimeout(async () => {
    try {
      // eslint-disable-next-line @typescript-eslint/no-var-requires
      const AsyncStorage = require('@react-native-async-storage/async-storage').default;
      await AsyncStorage.setItem(PERF_STORAGE_KEY, JSON.stringify(_perfLog.slice(-PERF_LOG_MAX)));
    } catch { /* swallow */ }
  }, 1500);
}

export function getPerfLog(): PerfSample[] {
  return _perfLog.slice();
}

export function clearPerfLog(): void {
  _perfLog.length = 0;
  _perfListeners.forEach(l => { try { l([]); } catch { /* swallow */ } });
  _schedulePerfFlush();
}

export function subscribePerf(listener: (log: PerfSample[]) => void): () => void {
  _perfListeners.add(listener);
  return () => { _perfListeners.delete(listener); };
}

function _recordPerf(name: string, ms: number) {
  const slow = ms > SLOW_RENDER_MS;
  _perfLog.push({ name, ms, ts: Date.now(), slow });
  if (_perfLog.length > PERF_LOG_MAX) _perfLog.splice(0, _perfLog.length - PERF_LOG_MAX);
  _perfListeners.forEach(l => { try { l(_perfLog.slice()); } catch { /* swallow */ } });
  _schedulePerfFlush();
}

export function useRenderTrace(name: string) {
  const t0 = useRef<number>(Date.now());

  useEffect(() => {
    const ms = Date.now() - t0.current;
    _recordPerf(name, ms);
    // Flag-gated: telemetry/trace recording only when auto_render_trace is on.
    const traceEnabled = getFeatureFlag('auto_render_trace');
    if (ms > SLOW_RENDER_MS) {
      // eslint-disable-next-line no-console
      console.warn(`[perf] slow render ${name}: ${ms}ms`);
      if (traceEnabled) {
        try {
          recordEvent(name, 'slow_render', 'warn', { ms });
          traceStep(`slow_render ${name} ${ms}ms`).catch(() => {});
        } catch { /* swallow */ }
      }
    } else if (traceEnabled) {
      // Cheap trace so /safe-mode shows what mounted recently.
      traceStep(`mount:${name} ${ms}ms`).catch(() => {});
    }
  }, [name]);
}

export function useDebounced<T>(value: T, ms = 250): T {
  const [out, setOut] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setOut(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return out;
}

export function useThrottled<T>(value: T, ms = 250): T {
  const [out, setOut] = useState(value);
  const last = useRef<number>(0);
  useEffect(() => {
    const now = Date.now();
    if (now - last.current >= ms) {
      last.current = now;
      setOut(value);
    } else {
      const id = setTimeout(() => {
        last.current = Date.now();
        setOut(value);
      }, ms - (now - last.current));
      return () => clearTimeout(id);
    }
  }, [value, ms]);
  return out;
}

export function useStableCallback<T extends (...args: any[]) => any>(fn: T): T {
  const ref = useRef(fn);
  useEffect(() => { ref.current = fn; });
  return useCallback(((...args: any[]) => ref.current(...args)) as T, []);
}

export function useDeferredHeavy<T>(compute: () => T, fallback: T): T {
  const [val, setVal] = useState<T>(fallback);
  useEffect(() => {
    const task = InteractionManager.runAfterInteractions(() => {
      try {
        const next = compute();
        setVal(next);
      } catch { /* swallow */ }
    });
    return () => { try { task.cancel(); } catch { /* swallow */ } };
    // compute is intentionally not in deps — caller decides via key prop
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return val;
}

// ── TTL memoization cache ───────────────────────────────────────────
interface CacheEntry<T> { value: T; expiresAt: number; }

export function memoCache<T>(ttlMs = 5000) {
  const store = new Map<string, CacheEntry<T>>();
  return {
    get(key: string): T | undefined {
      const e = store.get(key);
      if (!e) return undefined;
      if (Date.now() > e.expiresAt) { store.delete(key); return undefined; }
      return e.value;
    },
    set(key: string, value: T): void {
      store.set(key, { value, expiresAt: Date.now() + ttlMs });
    },
    clear(): void { store.clear(); },
    size(): number { return store.size; },
  };
}

// ── Heavy-list constants ────────────────────────────────────────────
export const FLATLIST_PERF_PROPS = {
  initialNumToRender:  8,
  maxToRenderPerBatch: 8,
  windowSize:          11,
  removeClippedSubviews: true,
  updateCellsBatchingPeriod: 50,
};

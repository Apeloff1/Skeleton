/**
 * src/hooks/index.ts — Reusable performance + lifecycle hooks (Feb 2026).
 *
 * Re-exports + a handful of standalone helpers that wrap React patterns
 * we keep repeating across screens:
 *
 *   useIsMounted()      — prevents setState-after-unmount warnings.
 *   useDebounced(v, ms) — returns a debounced copy of v.
 *   useThrottled(fn,ms) — fires fn at most once per ms.
 *   usePrevious(v)      — reads the previous render's value.
 *   useStableCallback() — returns a stable fn ref that calls latest impl.
 *   useFetch(path)      — hook-shaped wrapper around apiClient with
 *                          loading/error/refetch state.
 *   useInteraction()    — schedules work after the next interaction
 *                          (defers non-critical effects).
 */
import React from 'react';
import { InteractionManager } from 'react-native';
import api, { ApiResult } from '../utils/apiClient';

export function useIsMounted() {
  const ref = React.useRef(true);
  React.useEffect(() => { ref.current = true; return () => { ref.current = false; }; }, []);
  return React.useCallback(() => ref.current, []);
}

export function useDebounced<T>(value: T, delay: number = 250): T {
  const [v, setV] = React.useState(value);
  React.useEffect(() => {
    const t = setTimeout(() => setV(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return v;
}

export function useThrottled<T extends (...args: any[]) => void>(fn: T, ms: number = 200): T {
  const lastRef = React.useRef<number>(0);
  const fnRef   = React.useRef<T>(fn);
  React.useEffect(() => { fnRef.current = fn; }, [fn]);
  return React.useCallback(((...args: any[]) => {
    const now = Date.now();
    if (now - lastRef.current >= ms) {
      lastRef.current = now;
      fnRef.current(...args);
    }
  }) as T, [ms]);
}

export function usePrevious<T>(value: T): T | undefined {
  const ref = React.useRef<T | undefined>(undefined);
  React.useEffect(() => { ref.current = value; }, [value]);
  return ref.current;
}

export function useStableCallback<T extends (...args: any[]) => any>(fn: T): T {
  const ref = React.useRef(fn);
  React.useEffect(() => { ref.current = fn; }, [fn]);
  return React.useCallback(((...args: any[]) => ref.current(...args)) as T, []);
}

export function useInteraction(fn: () => void, deps: any[] = []) {
  React.useEffect(() => {
    const h = InteractionManager.runAfterInteractions(fn);
    return () => { try { (h as any)?.cancel?.(); } catch {} };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}

export interface UseFetchState<T> {
  data:    T | null;
  loading: boolean;
  error:   string | null;
  status:  number;
  refetch: () => Promise<void>;
  rid:     string | null;
}

/** Hook wrapper around apiClient.get with loading/error/refetch state. */
export function useFetch<T = any>(
  path: string | null,
  opts: { cacheKey?: string; cacheTtlMs?: number; eager?: boolean } = { eager: true },
): UseFetchState<T> {
  const [data,    setData]    = React.useState<T | null>(null);
  const [error,   setError]   = React.useState<string | null>(null);
  const [status,  setStatus]  = React.useState<number>(0);
  const [rid,     setRid]     = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState<boolean>(!!opts.eager && !!path);
  const isMounted = useIsMounted();

  const doFetch = React.useCallback(async () => {
    if (!path) return;
    setLoading(true); setError(null);
    const r: ApiResult<T> = await api.get<T>(path, { cacheKey: opts.cacheKey, cacheTtlMs: opts.cacheTtlMs });
    if (!isMounted()) return;
    setData(r.data); setError(r.error); setStatus(r.status); setRid(r.rid);
    setLoading(false);
  }, [path, opts.cacheKey, opts.cacheTtlMs, isMounted]);

  React.useEffect(() => {
    if (opts.eager === false) return;
    void doFetch();
  }, [doFetch, opts.eager]);

  return { data, loading, error, status, refetch: doFetch, rid };
}

export { default as useHaptics } from './useHaptics';
export { default as useReduceMotion } from './useReduceMotion';

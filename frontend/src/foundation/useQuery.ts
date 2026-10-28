/**
 * `useQuery` — cached, de-duplicated data fetching with uniform states.
 * Backed by the framework-free QueryCache in queryCache.ts.
 *
 * This hook does not open its own connection. Fetchers must call the single
 * TypeScript HTTP transport in src/utils/apiClient.ts (`api` or `safeGetJson`).
 */
import { useCallback, useEffect, useRef, useSyncExternalStore } from 'react';
import { appQueryCache, QueryCache, QueryKey, QueryState, serializeKey, viewStateOf, ViewState } from './queryCache';

export interface UseQueryOptions<T> {
  enabled?: boolean;
  staleTimeMs?: number;
  cache?: QueryCache;
  isEmpty?: (data: T) => boolean;
}

export interface UseQueryResult<T> extends QueryState<T> {
  view: ViewState;
  refetch: () => Promise<T | undefined>;
}

export function useQuery<T>(key: QueryKey, fetcher: () => Promise<T>, opts: UseQueryOptions<T> = {}): UseQueryResult<T> {
  const { enabled = true, staleTimeMs = 30_000, cache = appQueryCache, isEmpty } = opts;
  const id = serializeKey(key);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const subscribe = useCallback((cb: () => void) => cache.subscribe(id, cb), [cache, id]);
  const getSnapshot = useCallback(() => cache.get<T>(id), [cache, id]);
  const state = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);

  useEffect(() => {
    if (!enabled) return;
    cache.fetch(id, () => fetcherRef.current(), { staleTimeMs }).catch(() => {});
  }, [cache, id, enabled, staleTimeMs]);

  const refetch = useCallback(
    () => cache.fetch(id, () => fetcherRef.current(), { force: true }).catch(() => undefined),
    [cache, id],
  );

  return { ...state, view: enabled ? viewStateOf(state, isEmpty) : 'loading', refetch };
}

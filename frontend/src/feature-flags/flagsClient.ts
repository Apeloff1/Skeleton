/**
 * Feature-flag client with short-lived, user-scoped in-memory deduplication.
 */
import api from '../utils/apiClient';

export interface ResolvedFlag {
  name: string;
  description: string;
  enabled: boolean;
  rollout: number;
  environments: string[];
  resolved: boolean;
  updated_at?: number;
}

export interface FlagsSnapshot {
  ok: boolean;
  environment: string;
  user_id: string | null;
  flags: ResolvedFlag[];
  fetched_at: number;
}

export interface LoadFlagsOptions {
  force?: boolean;
  timeoutMs?: number;
  retries?: number;
}

const CACHE_TTL_MS = 60_000;
let cache: FlagsSnapshot | null = null;
let cacheKey: string | null = null;
let inflight: { key: string; promise: Promise<FlagsSnapshot> } | null = null;

function keyFor(userId: string | null): string {
  return userId || '_anon_';
}

/** Reads the last successful cached snapshot without I/O. */
export function snapshot(): FlagsSnapshot | null {
  return cache;
}

/** Forces a refetch on the next loadFlags call. */
export function invalidate(): void {
  cache = null;
  cacheKey = null;
  inflight = null;
}

export async function loadFlags(
  userId: string | null = null,
  opts: LoadFlagsOptions = {},
): Promise<FlagsSnapshot> {
  const key = keyFor(userId);
  if (
    !opts.force &&
    cache &&
    cacheKey === key &&
    (Date.now() - cache.fetched_at) < CACHE_TTL_MS
  ) {
    return cache;
  }

  if (inflight?.key === key) return inflight.promise;

  const path = userId
    ? `/api/feature-flags?user_id=${encodeURIComponent(userId)}`
    : '/api/feature-flags';

  let request!: Promise<FlagsSnapshot>;
  request = (async () => {
    const response = await api.get<{
      ok: boolean;
      environment: string;
      user_id: string | null;
      flags: ResolvedFlag[];
    }>(path, {
      cacheKey: `ff:${key}`,
      cacheTtlMs: CACHE_TTL_MS,
      timeoutMs: opts.timeoutMs ?? 6_000,
      retries: opts.retries ?? 1,
    });

    const result: FlagsSnapshot = {
      ok: !!response.ok,
      environment: response.data?.environment || 'unknown',
      user_id: response.data?.user_id ?? userId,
      flags: Array.isArray(response.data?.flags) ? response.data!.flags : [],
      fetched_at: Date.now(),
    };

    // A transient network failure must not poison the 60s cache or replace a
    // previously healthy snapshot with an empty one. The provider can retry in
    // the background while continuing to render its bundled/last-known flags.
    if (result.ok) {
      cache = result;
      cacheKey = key;
    }
    return result;
  })().finally(() => {
    if (inflight?.promise === request) inflight = null;
  });

  inflight = { key, promise: request };
  return request;
}

export function isEnabledCached(name: string, fallback: boolean = false): boolean {
  if (!cache) return fallback;
  const flag = cache.flags.find(item => item.name === name);
  return flag ? flag.resolved : fallback;
}

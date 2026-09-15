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
const cacheByKey = new Map<string, FlagsSnapshot>();
const inflightByKey = new Map<string, Promise<FlagsSnapshot>>();
let lastCacheKey: string | null = null;
let generation = 0;

function keyFor(userId: string | null): string {
  return userId || '_anon_';
}

/**
 * Reads the last successful cached snapshot without I/O.
 * Pass a user id to avoid ever consuming another user's resolved rollout.
 * Calling without an argument preserves the legacy "last snapshot" behavior.
 */
export function snapshot(userId?: string | null): FlagsSnapshot | null {
  if (arguments.length > 0) return cacheByKey.get(keyFor(userId ?? null)) || null;
  return lastCacheKey ? cacheByKey.get(lastCacheKey) || null : null;
}

/** Forces a refetch on the next loadFlags call and invalidates stale inflight ownership. */
export function invalidate(): void {
  generation += 1;
  cacheByKey.clear();
  inflightByKey.clear();
  lastCacheKey = null;
}

export async function loadFlags(
  userId: string | null = null,
  opts: LoadFlagsOptions = {},
): Promise<FlagsSnapshot> {
  const key = keyFor(userId);
  const cached = cacheByKey.get(key);
  if (!opts.force && cached && (Date.now() - cached.fetched_at) < CACHE_TTL_MS) {
    return cached;
  }

  const existing = inflightByKey.get(key);
  if (existing) return existing;

  const requestGeneration = generation;
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

    // Never cache a transient failure, and never let a request that started
    // before invalidate() repopulate a cache that an explicit refresh cleared.
    if (result.ok && requestGeneration === generation) {
      cacheByKey.set(key, result);
      lastCacheKey = key;
    }
    return result;
  })().finally(() => {
    if (inflightByKey.get(key) === request) inflightByKey.delete(key);
  });

  inflightByKey.set(key, request);
  return request;
}

export function isEnabledCached(name: string, fallback: boolean = false): boolean {
  const cached = lastCacheKey ? cacheByKey.get(lastCacheKey) : null;
  if (!cached) return fallback;
  const flag = cached.flags.find(item => item.name === name);
  return flag ? flag.resolved : fallback;
}

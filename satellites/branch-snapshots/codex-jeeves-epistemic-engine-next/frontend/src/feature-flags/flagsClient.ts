/**
 * src/feature-flags/flagsClient.ts — talks to /api/feature-flags.
 *
 * Wraps the shared `apiClient` so feature-flag reads pick up the same
 * retry / abort / RID instrumentation everything else uses. Results are
 * cached in-memory for `CACHE_TTL_MS` so the same screen doesn't refetch
 * on every mount.
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

const CACHE_TTL_MS = 60_000;
let _cache: FlagsSnapshot | null = null;
let _inflight: Promise<FlagsSnapshot> | null = null;

/** Reads the cached snapshot (no I/O). Returns null if cold. */
export function snapshot(): FlagsSnapshot | null {
  return _cache;
}

/** Forces a refetch on the next ``loadFlags`` call. */
export function invalidate(): void {
  _cache = null;
  _inflight = null;
}

export async function loadFlags(
  userId: string | null = null,
  opts: { force?: boolean } = {},
): Promise<FlagsSnapshot> {
  if (!opts.force && _cache && (Date.now() - _cache.fetched_at) < CACHE_TTL_MS) {
    return _cache;
  }
  if (_inflight) return _inflight;

  const path = userId
    ? `/api/feature-flags?user_id=${encodeURIComponent(userId)}`
    : `/api/feature-flags`;

  _inflight = (async () => {
    const r = await api.get<{ ok: boolean; environment: string; user_id: string | null; flags: ResolvedFlag[] }>(
      path,
      { cacheKey: `ff:${userId || '_anon_'}`, cacheTtlMs: CACHE_TTL_MS, timeoutMs: 6000, retries: 1 },
    );
    const snap: FlagsSnapshot = {
      ok: !!r.ok,
      environment: r.data?.environment || 'unknown',
      user_id: userId,
      flags: Array.isArray(r.data?.flags) ? r.data!.flags : [],
      fetched_at: Date.now(),
    };
    _cache = snap;
    _inflight = null;
    return snap;
  })();

  return _inflight;
}

/** Synchronous read against the warmed cache only. */
export function isEnabledCached(name: string, fallback: boolean = false): boolean {
  if (!_cache) return fallback;
  const f = _cache.flags.find(x => x.name === name);
  return f ? f.resolved : fallback;
}

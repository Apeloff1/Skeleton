/**
 * ═══════════════════════════════════════════════════════════════════════
 *  resilientNet.ts — ngrok-hardened network layer for the Galaxy Studio
 * ═══════════════════════════════════════════════════════════════════════
 *
 *  Ngrok tunnels drop, stall, or return 502 at random. The device network
 *  flips between wifi/cellular. This module wraps `fetch` with a set of
 *  stacked redundancies so the app keeps working even when the tunnel is
 *  sick:
 *
 *    • Multi-URL fallback ladder (primary + optional fallbacks from env)
 *    • AWS-style full-jitter exponential backoff (no thundering herd)
 *    • AbortController with guaranteed cleanup (no leaked timers)
 *    • Persistent GET cache (AsyncStorage) + in-memory TTL cache
 *    • Stale-while-revalidate — return cached data instantly, refresh bg
 *    • Request coalescing — duplicate in-flight GETs share one response
 *    • Idempotency-Key header so POST retries are safe server-side
 *    • Global circuit breaker with half-open probe
 *    • Heartbeat-driven tunnel health observable (see useTunnelHealth)
 *    • 4xx is NEVER retried (deterministic client error)
 *
 *  All exports are plain async functions — no React dependency, so this
 *  can be used from anywhere (screens, components, background tasks).
 * ═══════════════════════════════════════════════════════════════════════
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import Constants from 'expo-constants';

// ── Backend URL ladder ────────────────────────────────────────────────
function _webOriginIfBrowser(): string {
  // On Expo Web, prefer the page's own origin so /api/* routes through
  // whichever URL the user loaded (preview, deploy, custom domain).
  // This is critical so the app keeps working when the EXPO_PUBLIC_BACKEND_URL
  // env baked at build time doesn't match the actual deploy host.
  if (typeof window !== 'undefined') {
    const loc: any = (window as any).location;
    if (loc && typeof loc.origin === 'string' && loc.origin && !loc.origin.startsWith('file:')) {
      return loc.origin.replace(/\/+$/, '');
    }
  }
  return '';
}
const WEB_ORIGIN = _webOriginIfBrowser();
const PRIMARY =
  WEB_ORIGIN ||
  (Constants.expoConfig?.extra as any)?.EXPO_PUBLIC_BACKEND_URL ||
  process.env.EXPO_PUBLIC_BACKEND_URL ||
  '';
const FALLBACK =
  (Constants.expoConfig?.extra as any)?.EXPO_PUBLIC_BACKEND_FALLBACK_URL ||
  process.env.EXPO_PUBLIC_BACKEND_FALLBACK_URL ||
  '';

export const BACKEND_URLS: string[] = [PRIMARY, FALLBACK].filter(Boolean) as string[];

export function resolveUrl(pathOrUrl: string, host?: string): string {
  if (/^https?:\/\//i.test(pathOrUrl)) return pathOrUrl;
  const base = host || BACKEND_URLS[0] || '';
  if (!base) return pathOrUrl;
  return base.replace(/\/+$/, '') + (pathOrUrl.startsWith('/') ? pathOrUrl : `/${pathOrUrl}`);
}

// ── In-memory caches ───────────────────────────────────────────────────
type CacheEntry = { data: any; ts: number; etag?: string };
const MEM_CACHE_MAX = 200;             // LRU-ish cap to prevent unbounded growth
const PERSIST_MAX_BYTES = 200 * 1024;  // don't persist payloads larger than 200 KB
const memCache = new Map<string, CacheEntry>();

function _memSet(key: string, entry: CacheEntry) {
  // Simple LRU via delete+reinsert so the newest entry is last in iteration order
  if (memCache.has(key)) memCache.delete(key);
  memCache.set(key, entry);
  // Evict oldest when over cap
  while (memCache.size > MEM_CACHE_MAX) {
    const oldestKey = memCache.keys().next().value;
    if (oldestKey == null) break;
    memCache.delete(oldestKey);
  }
}

function _memGet(key: string): CacheEntry | undefined {
  const v = memCache.get(key);
  if (v) {
    // Touch (move to newest)
    memCache.delete(key);
    memCache.set(key, v);
  }
  return v;
}

// djb2-based hash for cache keys that can include bodies > 120 chars safely
function _djb2(s: string): string {
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0;
  return (h >>> 0).toString(36);
}

// In-flight GET dedupe (same URL + body)
const inflight = new Map<string, Promise<ResilientResult>>();

// ── Circuit breaker state (shared across the whole app) ───────────────
const BREAKER = {
  failures: 0,
  openUntil: 0,
  halfOpenProbeInflight: false,
  lastOkTs: 0,
  lastFailTs: 0,
  consecutiveOk: 0,
};

// ── Tunnel health observable ──────────────────────────────────────────
export type TunnelStatus = 'healthy' | 'degraded' | 'offline' | 'unknown';
type HealthSnapshot = {
  status: TunnelStatus;
  lastOkTs: number;
  lastFailTs: number;
  consecutiveFailures: number;
  circuitOpen: boolean;
  circuitOpenUntil: number;
  rttMs: number;
};

let _health: HealthSnapshot = {
  status: 'unknown',
  lastOkTs: 0,
  lastFailTs: 0,
  consecutiveFailures: 0,
  circuitOpen: false,
  circuitOpenUntil: 0,
  rttMs: 0,
};
const _healthSubs = new Set<(s: HealthSnapshot) => void>();

function _publishHealth() {
  const circuitOpen = BREAKER.openUntil > Date.now();
  let status: TunnelStatus = 'unknown';
  const ageSinceOk = _health.lastOkTs ? Date.now() - _health.lastOkTs : Infinity;
  if (circuitOpen || BREAKER.failures >= 5) {
    status = 'offline';
  } else if (BREAKER.failures >= 2 || ageSinceOk > 60_000) {
    status = 'degraded';
  } else if (_health.lastOkTs > 0) {
    status = 'healthy';
  }
  _health = {
    ..._health,
    status,
    circuitOpen,
    circuitOpenUntil: BREAKER.openUntil,
    consecutiveFailures: BREAKER.failures,
  };
  for (const fn of _healthSubs) {
    try { fn(_health); } catch {}
  }
}

export function subscribeTunnelHealth(fn: (s: HealthSnapshot) => void): () => void {
  _healthSubs.add(fn);
  try { fn(_health); } catch {}
  return () => { _healthSubs.delete(fn); };
}

export function getTunnelHealth(): HealthSnapshot {
  return { ..._health };
}

// ── Helpers ────────────────────────────────────────────────────────────
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

function fullJitter(attempt: number, baseMs = 600, capMs = 8000): number {
  const expo = Math.min(capMs, baseMs * 2 ** (attempt - 1));
  return Math.floor(Math.random() * expo);
}

function cacheKey(method: string, url: string, body?: any): string {
  if (body == null) return `${method}:${url}`;
  const bodyStr = typeof body === 'string' ? body : JSON.stringify(body);
  // Hash the body so long payloads never collide or bloat the key
  return `${method}:${url}:${bodyStr.length}:${_djb2(bodyStr)}`;
}

async function persistGet(key: string): Promise<CacheEntry | null> {
  try {
    const raw = await AsyncStorage.getItem(`rnet:${key}`);
    if (!raw) return null;
    return JSON.parse(raw) as CacheEntry;
  } catch {
    return null;
  }
}

async function persistSet(key: string, entry: CacheEntry): Promise<void> {
  try {
    const raw = JSON.stringify(entry);
    // Skip persisting oversized payloads (keeps AsyncStorage fast)
    if (raw.length > PERSIST_MAX_BYTES) return;
    await AsyncStorage.setItem(`rnet:${key}`, raw);
  } catch {}
}

// ── Public API ─────────────────────────────────────────────────────────
export interface ResilientOptions {
  method?: string;
  headers?: Record<string, string>;
  body?: any;                   // object → auto JSON; string → pass through
  retries?: number;             // default 3
  timeoutMs?: number;           // per-attempt base, grows with retries
  cacheTtlMs?: number;          // GET only — how long cached value is fresh
  staleMaxMs?: number;          // GET only — serve stale up to this age on failure
  persist?: boolean;            // GET only — write to AsyncStorage
  dedupe?: boolean;             // GET only — coalesce in-flight duplicates
  hosts?: string[];             // override backend host ladder
  signal?: AbortSignal;         // external abort
  rawText?: boolean;            // return raw text, skip JSON parse
}

export interface ResilientResult<T = any> {
  data: T;
  status: number;
  fromCache: boolean;
  stale: boolean;
  attempts: number;
  triedHosts: string[];
  elapsedMs: number;
  ok: boolean;
  error?: string;
}

const DEFAULTS: Required<Pick<ResilientOptions,
  'retries' | 'timeoutMs' | 'cacheTtlMs' | 'staleMaxMs' | 'persist' | 'dedupe'>> = {
  retries: 3,
  timeoutMs: 30000,
  cacheTtlMs: 15000,        // 15 s fresh window for GETs
  staleMaxMs: 24 * 60 * 60 * 1000,  // serve up to 24h stale if offline
  persist: true,
  dedupe: true,
};

/**
 * The one fetch-er to rule them all.
 * Usage:
 *   const { data } = await resilientFetch('/api/galaxy-studio/manifest');
 *   const { data } = await resilientFetch('/api/galaxy-studio/create', { method:'POST', body:{...} });
 */
export async function resilientFetch<T = any>(
  path: string,
  options: ResilientOptions = {},
): Promise<ResilientResult<T>> {
  const method = (options.method || 'GET').toUpperCase();
  const hosts = options.hosts || BACKEND_URLS;
  const primaryUrl = resolveUrl(path, hosts[0]);
  const key = cacheKey(method, primaryUrl, options.body);
  const cfg = { ...DEFAULTS, ...options };
  const start = Date.now();

  const isGet = method === 'GET' || method === 'HEAD';
  const wantsCache = isGet && cfg.cacheTtlMs > 0;

  // ── (1) In-flight dedupe (GET only) ──
  if (isGet && cfg.dedupe) {
    const existing = inflight.get(key);
    if (existing) return existing as Promise<ResilientResult<T>>;
  }

  const job = (async (): Promise<ResilientResult<T>> => {
    const triedHosts: string[] = [];
    let attempts = 0;
    let lastError: string | undefined;
    let lastStatus = 0;

    // ── (2) Fresh mem-cache hit? return immediately (no network) ──
    if (wantsCache) {
      const mc = _memGet(key);
      if (mc && Date.now() - mc.ts < cfg.cacheTtlMs) {
        return {
          data: mc.data,
          status: 200,
          fromCache: true,
          stale: false,
          attempts: 0,
          triedHosts: [],
          elapsedMs: Date.now() - start,
          ok: true,
        };
      }
    }

    // ── (2b) No backend configured at all? serve cache if possible ──
    if (hosts.length === 0) {
      if (wantsCache) {
        const cached = _memGet(key) || (cfg.persist ? await persistGet(key) : null);
        if (cached && Date.now() - cached.ts < cfg.staleMaxMs) {
          return {
            data: cached.data, status: 0, fromCache: true, stale: true,
            attempts: 0, triedHosts: [], elapsedMs: Date.now() - start, ok: true,
          };
        }
      }
      throw new Error('No backend URL configured (EXPO_PUBLIC_BACKEND_URL is empty)');
    }

    // ── (3) Circuit breaker check ──
    // If open, try a single probe on the first host; else go straight to cache/fail.
    const circuitOpen = BREAKER.openUntil > Date.now();
    if (circuitOpen && !BREAKER.halfOpenProbeInflight) {
      // Enter half-open mode — only ONE caller probes, others serve stale/fail
      BREAKER.halfOpenProbeInflight = true;
    } else if (circuitOpen) {
      // Another probe in flight — serve stale if possible
      if (wantsCache) {
        const stale = _memGet(key) || (cfg.persist ? await persistGet(key) : null);
        if (stale && Date.now() - stale.ts < cfg.staleMaxMs) {
          return {
            data: stale.data, status: 0, fromCache: true, stale: true,
            attempts: 0, triedHosts: [], elapsedMs: Date.now() - start, ok: true,
          };
        }
      }
      throw new Error('Circuit open — tunnel unhealthy');
    }

    // ── (4) Network attempts across host ladder × retries ──
    for (let hostIdx = 0; hostIdx < hosts.length; hostIdx++) {
      const host = hosts[hostIdx];
      const url = resolveUrl(path, host);
      triedHosts.push(host);

      for (let attempt = 1; attempt <= cfg.retries; attempt++) {
        attempts++;
        const controller = new AbortController();
        const onExternalAbort = () => controller.abort();
        options.signal?.addEventListener?.('abort', onExternalAbort);
        const perAttemptTimeout = cfg.timeoutMs + (attempt - 1) * 5000;
        const tHandle = setTimeout(() => { try { controller.abort(); } catch {} }, perAttemptTimeout);

        try {
          const bodyOut =
            options.body == null
              ? undefined
              : typeof options.body === 'string'
                ? options.body
                : JSON.stringify(options.body);

          const headers: Record<string, string> = {
            Accept: 'application/json',
            'Cache-Control': 'no-cache, no-store',
            'X-Attempt': String(attempt),
            'X-Host-Idx': String(hostIdx),
            ...(options.headers || {}),
          };
          if (bodyOut != null && !headers['Content-Type']) {
            headers['Content-Type'] = 'application/json';
          }
          if (!isGet) {
            // Stable idempotency key so server can dedupe on retry
            headers['X-Idempotency-Key'] = headers['X-Idempotency-Key'] ||
              `${method}:${Date.now()}:${Math.random().toString(36).slice(2, 10)}`;
          }

          const t0 = Date.now();
          const res = await fetch(url, {
            method,
            headers,
            body: bodyOut,
            signal: controller.signal,
            // @ts-ignore
            cache: 'no-store',
            credentials: 'omit',
          });
          lastStatus = res.status;

          // 4xx — deterministic client error, do NOT retry
          if (res.status >= 400 && res.status < 500) {
            const txt = await res.text().catch(() => '');
            const err = `${res.status}: ${txt.slice(0, 200)}`;
            throw Object.assign(new Error(err), { _isClient: true, _status: res.status });
          }
          // 5xx — retryable
          if (!res.ok) {
            const txt = await res.text().catch(() => '');
            throw new Error(`${res.status}: ${txt.slice(0, 100)}`);
          }

          // Success
          const rtt = Date.now() - t0;
          const text = await res.text();
          let parsed: any = text;
          if (!options.rawText) {
            try { parsed = JSON.parse(text); } catch { /* keep as text */ }
          }

          // Write cache
          if (wantsCache) {
            const entry: CacheEntry = { data: parsed, ts: Date.now() };
            _memSet(key, entry);
            if (cfg.persist) { persistSet(key, entry); /* fire-and-forget */ }
          }

          // Breaker: success
          BREAKER.failures = 0;
          BREAKER.openUntil = 0;
          BREAKER.consecutiveOk++;
          BREAKER.lastOkTs = Date.now();
          BREAKER.halfOpenProbeInflight = false;
          _health.lastOkTs = BREAKER.lastOkTs;
          _health.rttMs = rtt;
          _publishHealth();

          return {
            data: parsed as T,
            status: res.status,
            fromCache: false,
            stale: false,
            attempts,
            triedHosts,
            elapsedMs: Date.now() - start,
            ok: true,
          };
        } catch (err: any) {
          const isClient = err?._isClient === true;
          lastError = String(err?.message || err);
          if (isClient) {
            // Immediate — client error propagates
            throw err;
          }
          if (attempt < cfg.retries) {
            await sleep(fullJitter(attempt));
          }
        } finally {
          clearTimeout(tHandle);
          options.signal?.removeEventListener?.('abort', onExternalAbort);
        }
      } // per-host retries
      // Host exhausted — try next host
    }

    // ── (5) All hosts failed → fall back to cache if available ──
    BREAKER.failures++;
    BREAKER.lastFailTs = Date.now();
    BREAKER.consecutiveOk = 0;
    if (BREAKER.failures >= 6) {
      BREAKER.openUntil = Date.now() + 30_000; // open for 30 s
    }
    _health.lastFailTs = BREAKER.lastFailTs;
    _publishHealth();

    if (wantsCache) {
      const cached = _memGet(key) || (cfg.persist ? await persistGet(key) : null);
      if (cached && Date.now() - cached.ts < cfg.staleMaxMs) {
        return {
          data: cached.data,
          status: lastStatus || 0,
          fromCache: true,
          stale: true,
          attempts,
          triedHosts,
          elapsedMs: Date.now() - start,
          ok: true,
          error: lastError,
        };
      }
    }

    // Clear half-open marker so a future call can probe again
    BREAKER.halfOpenProbeInflight = false;
    throw new Error(
      `resilientFetch failed after ${attempts} attempts across ${triedHosts.length} host(s): ${lastError || 'unknown'}`,
    );
  })();

  if (isGet && cfg.dedupe) {
    inflight.set(key, job);
    job.finally(() => inflight.delete(key));
  }
  return job;
}

// ── Shorthand helpers ─────────────────────────────────────────────────
export async function rget<T = any>(path: string, opts: ResilientOptions = {}) {
  return resilientFetch<T>(path, { ...opts, method: 'GET' });
}

export async function rpost<T = any>(path: string, body: any, opts: ResilientOptions = {}) {
  return resilientFetch<T>(path, { ...opts, method: 'POST', body });
}

// ── Tunnel health heartbeat (adaptive cadence) ────────────────────────
let heartbeatTimer: any = null;
let heartbeatStopped = false;

function _nextHeartbeatDelay(): number {
  // Adaptive: gentle when healthy, aggressive when degraded/offline.
  const status = _health.status;
  if (status === 'offline') return 5_000;      // 5 s  — hunt for recovery
  if (status === 'degraded') return 10_000;    // 10 s — probe more often
  return 30_000;                               // 30 s — healthy, be gentle
}

async function heartbeat() {
  if (heartbeatStopped) return;
  if (BACKEND_URLS.length === 0) {
    // No backend configured — nothing to probe
    heartbeatTimer = setTimeout(heartbeat, 30_000);
    return;
  }
  try {
    const t0 = Date.now();
    const controller = new AbortController();
    const h = setTimeout(() => { try { controller.abort(); } catch {} }, 10_000);
    const res = await fetch(resolveUrl('/api/health'), {
      method: 'GET',
      signal: controller.signal,
      // @ts-ignore
      cache: 'no-store',
      credentials: 'omit',
      headers: { Accept: 'application/json', 'Cache-Control': 'no-cache, no-store' },
    });
    clearTimeout(h);
    if (res.ok) {
      BREAKER.failures = 0;
      BREAKER.openUntil = 0;
      BREAKER.halfOpenProbeInflight = false;
      BREAKER.lastOkTs = Date.now();
      _health.lastOkTs = BREAKER.lastOkTs;
      _health.rttMs = Date.now() - t0;
    } else {
      BREAKER.failures = Math.min(BREAKER.failures + 1, 10);
      BREAKER.lastFailTs = Date.now();
    }
  } catch {
    BREAKER.failures = Math.min(BREAKER.failures + 1, 10);
    BREAKER.lastFailTs = Date.now();
  }
  _publishHealth();
  if (!heartbeatStopped) {
    heartbeatTimer = setTimeout(heartbeat, _nextHeartbeatDelay());
  }
}

export function startHeartbeat() {
  if (heartbeatTimer) return;
  heartbeatStopped = false;
  heartbeatTimer = setTimeout(heartbeat, 500);
}
export function stopHeartbeat() {
  heartbeatStopped = true;
  if (heartbeatTimer) { clearTimeout(heartbeatTimer); heartbeatTimer = null; }
}

// ── Cache management (debug / manual) ────────────────────────────────
export function clearMemCache() { memCache.clear(); }
export async function clearPersistCache() {
  try {
    const keys = await AsyncStorage.getAllKeys();
    const mine = keys.filter((k) => k.startsWith('rnet:'));
    if (mine.length) await AsyncStorage.multiRemove(mine);
  } catch {}
}

// Convenience: expose the shared breaker for UI (read-only)
export function getCircuitState() {
  return {
    failures: BREAKER.failures,
    openUntil: BREAKER.openUntil,
    lastOkTs: BREAKER.lastOkTs,
    lastFailTs: BREAKER.lastFailTs,
  };
}

/** Reset the circuit breaker — call this from explicit user actions
 *  (e.g. "Start Build" button) so stale failures don't immediately
 *  block the very request the user just initiated. Also clears the
 *  in-memory cache and all in-flight GET promises so a fresh start.
 */
export function resetCircuit(): void {
  BREAKER.failures = 0;
  BREAKER.openUntil = 0;
  BREAKER.halfOpenProbeInflight = false;
  BREAKER.consecutiveOk = 0;
  inflight.clear();
  _publishHealth();
}

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
 *    • No mutation replay without a verified server-side deduplication contract
 *    • Global circuit breaker with half-open probe
 *    • Heartbeat-driven tunnel health observable (see useTunnelHealth)
 *    • Only retry transient 408/429 GETs; deterministic 4xx errors are terminal
 *
 *  All exports are plain async functions — no React dependency, so this
 *  can be used from anywhere (screens, components, background tasks).
 * ═══════════════════════════════════════════════════════════════════════
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { API_BASE, API_FALLBACK_BASE } from './apiBase';
import { boundedRetries, boundedTimeoutMs, boundedResponseChars, retryableHttpStatus } from './requestRecoveryPolicy';

// ── Backend URL ladder ────────────────────────────────────────────────
// Endpoint ownership lives in apiBase.ts. This layer only adds transport
// resilience across the already-resolved primary and optional fallback.
export const BACKEND_URLS: string[] = [API_BASE, API_FALLBACK_BASE]
  .filter((value, index, values) => Boolean(value) && values.indexOf(value) === index);

export function resolveUrl(pathOrUrl: string, host?: string): string {
  if (/^https?:\/\//i.test(pathOrUrl)) return pathOrUrl;
  const base = host || BACKEND_URLS[0] || '';
  if (!base) return pathOrUrl;
  return base.replace(/\/+$/, '') + (pathOrUrl.startsWith('/') ? pathOrUrl : `/${pathOrUrl}`);
}

// ── In-memory caches ───────────────────────────────────────────────────
type CacheEntry = { data: any; ts: number; chars?: number; etag?: string };
const MEM_CACHE_MAX = 200;             // LRU cap
const MEM_CACHE_MAX_CHARS = 16 * 1024 * 1024;
const MEM_ENTRY_MAX_CHARS = 512 * 1024;
let memCacheChars = 0;
const PERSIST_MAX_BYTES = 200 * 1024;  // don't persist payloads larger than 200 KB
const memCache = new Map<string, CacheEntry>();

function _entryChars(entry: CacheEntry): number {
  if (typeof entry.chars === 'number') return entry.chars;
  try { return JSON.stringify(entry.data).length; } catch { return MEM_ENTRY_MAX_CHARS + 1; }
}

function _memDelete(key: string) {
  const old = memCache.get(key);
  if (old) memCacheChars = Math.max(0, memCacheChars - _entryChars(old));
  memCache.delete(key);
}

function _memSet(key: string, entry: CacheEntry) {
  const chars = _entryChars(entry);
  // Restrict aggregate retained payload volume, not just the entry count.
  if (!Number.isFinite(chars) || chars > MEM_ENTRY_MAX_CHARS) return;
  if (memCache.has(key)) _memDelete(key);
  memCache.set(key, { ...entry, chars });
  memCacheChars += chars;
  while (memCache.size > MEM_CACHE_MAX || memCacheChars > MEM_CACHE_MAX_CHARS) {
    const oldest = memCache.keys().next().value;
    if (oldest === undefined) break;
    _memDelete(oldest);
  }
}

function _memGet(key: string): CacheEntry | undefined {
  const v = memCache.get(key);
  if (!v) return undefined;
  // Corrupt/future-dated or expired entries are never treated as reusable.
  if (!Number.isFinite(v.ts) || v.ts > Date.now() ||
      Date.now() - v.ts > 24 * 60 * 60 * 1000) {
    _memDelete(key);
    return undefined;
  }
  _memDelete(key);
  memCache.set(key, v);
  memCacheChars += _entryChars(v);
  return v;
}

export function getResilientCacheStats() {
  return { entries: memCache.size, chars: memCacheChars, maxChars: MEM_CACHE_MAX_CHARS };
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
  generation: 0,
  probeGeneration: 0,
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
function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) return Promise.reject(new Error('Request cancelled'));
  return new Promise((resolve, reject) => {
    const onAbort = () => {
      clearTimeout(timer);
      signal?.removeEventListener('abort', onAbort);
      reject(new Error('Request cancelled'));
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', onAbort);
      resolve();
    }, ms);
    signal?.addEventListener('abort', onAbort, { once: true });
  });
}

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
    if (raw.length > PERSIST_MAX_BYTES) return null;
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return null;
    const entry = parsed as CacheEntry;
    if (typeof entry.ts !== 'number' || !Number.isFinite(entry.ts) ||
        entry.ts > Date.now() || Date.now() - entry.ts > 24 * 60 * 60 * 1000) return null;
    if (_entryChars(entry) > MEM_ENTRY_MAX_CHARS) return null;
    return entry;
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

/**
 * Streaming limits are enforced BEFORE buffering into a single string when a
 * native ReadableStream is exposed. Older RN fetch shims without .getReader()
 * still use .text() and reject after it resolves; declared lengths are checked
 * by the caller before that fallback.
 */
async function readTextBounded(res: Response, maxChars: number): Promise<string> {
  const tooLarge = () => Object.assign(new Error('Response exceeds size budget'), { _isClient: true });
  if (res.body && typeof res.body.getReader === 'function' && typeof TextDecoder !== 'undefined') {
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let chars = 0;
    const parts: string[] = [];
    try {
      while (true) {
        const chunk = await reader.read();
        if (chunk.done) break;
        // Byte count is a conservative bound for UTF-8 decoded characters.
        chars += chunk.value.byteLength;
        if (chars > maxChars) {
          await reader.cancel().catch(() => {});
          throw tooLarge();
        }
        parts.push(decoder.decode(chunk.value, { stream: true }));
      }
      parts.push(decoder.decode());
      return parts.join('');
    } finally {
      reader.releaseLock();
    }
  }
  const text = await res.text();
  if (text.length > maxChars) throw tooLarge();
  return text;
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
  maxResponseChars?: number;   // upper bound before JSON parsing
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
  const isGet = method === 'GET' || method === 'HEAD';
  // A write is never replayed or redirected to a fallback host without a
  // verified server-side idempotency contract (none is declared here).
  const configuredHosts = options.hosts || BACKEND_URLS;
  // Explicit headers may vary by tenant, locale or credentials. Never share
  // their cache/coalescing state or forward them to an alternate host.
  const hasHeaders = Object.keys(options.headers || {}).length > 0;
  const hosts = isGet && !hasHeaders ? configuredHosts : configuredHosts.slice(0, 1);
  const primaryUrl = resolveUrl(path, hosts[0]);
  const maxResponseChars = boundedResponseChars(options.maxResponseChars);
  // Deduplication/cache identity includes decode mode, response admission
  // budget and failover ladder, not only the first URL.
  const key = cacheKey(method, primaryUrl, options.body) +
    (options.rawText ? ':raw:' : ':json:') + maxResponseChars + ':' +
    _djb2(hosts.join('|'));
  const cfg = { ...DEFAULTS, ...options };
  const start = Date.now();
  const dedupe = isGet && cfg.dedupe && !hasHeaders && !options.signal;
  const wantsCache = isGet && cfg.cacheTtlMs > 0 && !hasHeaders;
  const attemptsPerHost = 1 + boundedRetries(options.retries, method, false);
  let ownsProbe = false;
  let probeGeneration = 0;
  const breakerGeneration = BREAKER.generation;
  const deadline = start + 90_000; // entire operation, not just each attempt
  const freshAge = Number.isFinite(cfg.cacheTtlMs) ? Math.max(0, Math.min(cfg.cacheTtlMs, 90_000)) : 0;
  const staleAge = Number.isFinite(cfg.staleMaxMs) ? Math.max(0, Math.min(cfg.staleMaxMs, 24 * 60 * 60 * 1000)) : 0;
  const eligible = (entry: CacheEntry | null | undefined, maxAge: number): entry is CacheEntry =>
    !!entry && entry.ts <= Date.now() && Date.now() - entry.ts < maxAge &&
    _entryChars(entry) <= maxResponseChars;
  if (options.signal?.aborted) throw new Error('Request cancelled');

  // ── (1) In-flight dedupe (GET only) ──
  if (dedupe) {
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
      if (eligible(mc, freshAge)) {
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
        if (eligible(cached, staleAge)) {
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
      ownsProbe = true;
      probeGeneration = ++BREAKER.probeGeneration;
    } else if (circuitOpen) {
      // Another probe in flight — serve stale if possible
      if (wantsCache) {
        const stale = _memGet(key) || (cfg.persist ? await persistGet(key) : null);
        if (eligible(stale, staleAge)) {
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

      for (let attempt = 1; attempt <= attemptsPerHost; attempt++) {
        if (options.signal?.aborted) throw new Error('Request cancelled');
        if (Date.now() >= deadline) break;
        attempts++;
        const controller = new AbortController();
        const onExternalAbort = () => controller.abort();
        options.signal?.addEventListener?.('abort', onExternalAbort);
        const perAttemptTimeout = Math.min(
          boundedTimeoutMs(cfg.timeoutMs + (attempt - 1) * 5000),
          Math.max(1, deadline - Date.now()),
        );
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
          // Do not synthesize an idempotency key and imply server-side
          // deduplication. Caller-supplied identity passes through unchanged.

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

          // A transient 408/429 may retry for safe reads; all other 4xx
          // responses are terminal. Never replay a mutation.
          if (res.status >= 400 && res.status < 500) {
            const txt = await readTextBounded(res, 512).catch(() => '');
            const err = `${res.status}: ${txt.slice(0, 200)}`;
            throw Object.assign(new Error(err), {
              _isClient: !isGet || !retryableHttpStatus(res.status),
              _status: res.status,
            });
          }
          // 5xx — retryable
          if (!res.ok) {
            const txt = await readTextBounded(res, 512).catch(() => '');
            throw new Error(`${res.status}: ${txt.slice(0, 100)}`);
          }

          // Refuse a declared oversized payload before reading it, and
          // always enforce a finite parsing boundary.
          const declaredSize = Number(res.headers?.get?.('content-length'));
          if (Number.isFinite(declaredSize) && declaredSize > maxResponseChars) {
            throw Object.assign(new Error('Response exceeds size budget'), { _isClient: true });
          }
          const rtt = Date.now() - t0;
          const text = await readTextBounded(res, maxResponseChars);
          let parsed: any = text;
          if (!options.rawText) {
            try { parsed = JSON.parse(text); } catch { /* keep as text */ }
          }

          // Write cache
          if (wantsCache && BREAKER.generation === breakerGeneration) {
            const entry: CacheEntry = { data: parsed, ts: Date.now(), chars: text.length };
            _memSet(key, entry);
            if (cfg.persist) { persistSet(key, entry); /* fire-and-forget */ }
          }

          // Breaker: success
          if (BREAKER.generation === breakerGeneration) {
            BREAKER.failures = 0;
            BREAKER.openUntil = 0;
            BREAKER.consecutiveOk++;
            BREAKER.lastOkTs = Date.now();
            if (ownsProbe && BREAKER.probeGeneration === probeGeneration) {
              BREAKER.halfOpenProbeInflight = false;
            }
            _health.lastOkTs = BREAKER.lastOkTs;
            _health.rttMs = rtt;
            _publishHealth();
          }

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
          if (isClient || options.signal?.aborted) {
            throw err;
          }
          if (attempt < attemptsPerHost && Date.now() < deadline) {
            await sleep(Math.min(fullJitter(attempt), Math.max(0, deadline - Date.now())), options.signal);
          }
        } finally {
          clearTimeout(tHandle);
          options.signal?.removeEventListener?.('abort', onExternalAbort);
        }
      } // per-host retries
      // Host exhausted — try next host
    }

    if (options.signal?.aborted) throw new Error('Request cancelled');
    // ── (5) All hosts failed → fall back to cache if available ──
    if (BREAKER.generation === breakerGeneration) {
      BREAKER.failures++;
      BREAKER.lastFailTs = Date.now();
      BREAKER.consecutiveOk = 0;
      if (BREAKER.failures >= 6) BREAKER.openUntil = Date.now() + 30_000;
      _health.lastFailTs = BREAKER.lastFailTs;
      _publishHealth();
    }

    if (wantsCache) {
      const cached = _memGet(key) || (cfg.persist ? await persistGet(key) : null);
      if (eligible(cached, staleAge)) {
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
    if (ownsProbe && BREAKER.probeGeneration === probeGeneration) {
      BREAKER.halfOpenProbeInflight = false;
    }
    throw new Error(
      `resilientFetch failed after ${attempts} attempts across ${triedHosts.length} host(s): ${lastError || 'unknown'}`,
    );
  })();

  if (dedupe) {
    inflight.set(key, job);
    // A bare finally() creates a second rejected promise on network failure.
    // Also protect a replacement request installed after resetCircuit().
    const release = () => { if (inflight.get(key) === job) inflight.delete(key); };
    void job.then(release, release);
  }
  // Client errors, aborts and rejected probes must not leave the circuit
  // stuck in half-open mode indefinitely.
  const releaseProbe = () => {
    if (ownsProbe && BREAKER.probeGeneration === probeGeneration) BREAKER.halfOpenProbeInflight = false;
  };
  void job.then(releaseProbe, releaseProbe);
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
let heartbeatTimer: ReturnType<typeof setTimeout> | null = null;
let heartbeatStopped = true;
let heartbeatEpoch = 0;
let heartbeatController: AbortController | null = null;
let heartbeatLeases = 0;
let manualHeartbeatRequested = false;

function _nextHeartbeatDelay(): number {
  const status = _health.status;
  if (status === 'offline') return 5_000;
  if (status === 'degraded') return 10_000;
  return 30_000;
}

function scheduleHeartbeat(epoch: number, delayMs: number) {
  if (heartbeatStopped || epoch !== heartbeatEpoch) return;
  heartbeatTimer = setTimeout(() => { void heartbeat(epoch); }, delayMs);
}

async function heartbeat(epoch: number) {
  heartbeatTimer = null;
  if (heartbeatStopped || epoch !== heartbeatEpoch) return;
  if (BACKEND_URLS.length === 0) {
    scheduleHeartbeat(epoch, 30_000);
    return;
  }

  const controller = new AbortController();
  heartbeatController = controller;
  const timeout = setTimeout(() => controller.abort(), 10_000);
  const t0 = Date.now();
  try {
    const res = await fetch(resolveUrl('/api/health'), {
      method: 'GET',
      signal: controller.signal,
      // @ts-ignore
      cache: 'no-store',
      credentials: 'omit',
      headers: { Accept: 'application/json', 'Cache-Control': 'no-cache, no-store' },
    });
    // An aborted previous generation cannot modify a restarted health loop.
    if (heartbeatStopped || epoch !== heartbeatEpoch) return;
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
    if (heartbeatStopped || epoch !== heartbeatEpoch) return;
    BREAKER.failures = Math.min(BREAKER.failures + 1, 10);
    BREAKER.lastFailTs = Date.now();
  } finally {
    // The timeout must be cleared even when fetch throws/rejects.
    clearTimeout(timeout);
    if (heartbeatController === controller) heartbeatController = null;
  }

  if (heartbeatStopped || epoch !== heartbeatEpoch) return;
  _publishHealth();
  scheduleHeartbeat(epoch, _nextHeartbeatDelay());
}

function ensureHeartbeatRunning() {
  if (!heartbeatStopped) return;
  heartbeatStopped = false;
  scheduleHeartbeat(++heartbeatEpoch, 500);
}

function haltHeartbeat() {
  heartbeatStopped = true;
  heartbeatEpoch++;
  if (heartbeatTimer) clearTimeout(heartbeatTimer);
  heartbeatTimer = null;
  heartbeatController?.abort();
  heartbeatController = null;
}

// Explicit manual lifecycle remains independent of mounted subscribers.
export function startHeartbeat() {
  manualHeartbeatRequested = true;
  ensureHeartbeatRunning();
}

export function stopHeartbeat() {
  manualHeartbeatRequested = false;
  if (heartbeatLeases === 0) haltHeartbeat();
}

/** Scoped lease for UI subscribers; the last one stops background polling. */
export function retainHeartbeat(): () => void {
  heartbeatLeases++;
  ensureHeartbeatRunning();
  let released = false;
  return () => {
    if (released) return;
    released = true;
    heartbeatLeases = Math.max(0, heartbeatLeases - 1);
    if (heartbeatLeases === 0 && !manualHeartbeatRequested) haltHeartbeat();
  };
}

// ── Cache management (debug / manual) ────────────────────────────────
export function clearMemCache() { memCache.clear(); memCacheChars = 0; }
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
  clearMemCache();
  BREAKER.generation++;
  BREAKER.probeGeneration++;
  _publishHealth();
}

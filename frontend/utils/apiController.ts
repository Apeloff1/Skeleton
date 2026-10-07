/**
 * apiController — SOTA frontend HTTP layer.
 *
 *   • Single source of truth for all backend calls.
 *   • Per-request timeout via AbortController.
 *   • Exponential-backoff retries with jitter on 5xx / network errors.
 *   • Request deduplication — identical GET in flight returns the same promise.
 *   • TTL-based response cache (in-memory + optional AsyncStorage persistence).
 *   • Offline detection (NetInfo) + retry-queue when back online.
 *   • Error normalisation — every failure returns the same shape.
 *   • Telemetry — request count, p50/p95 latency, error count, last error.
 *   • Pluggable Auth header hook.
 *
 * Usage:
 *   import { api } from '@/utils/apiController';
 *   const data = await api.get('/api/curriculum/classes');
 *   await api.post('/api/galaxy-studio/advance', { build_id });
 *
 * Configure once on app boot:
 *   api.configure({ defaultTimeoutMs: 12_000, retry: { max: 3 } });
 */
import { Platform } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { API_BASE } from './apiBase';

// ─────────────────────────────────────────────────────────────────────
// PUBLIC TYPES
// ─────────────────────────────────────────────────────────────────────
export interface RetryPolicy {
  max: number;
  /** Initial backoff in ms. Subsequent waits = base * 2^attempt + jitter. */
  baseMs: number;
  /** Max backoff in ms (cap). */
  capMs: number;
  /** Status codes that should be retried (5xx + 429 default). */
  retryStatus: number[];
}

export interface ApiOptions {
  /** Override the default timeout (ms). */
  timeoutMs?: number;
  /** Override the default retry policy. */
  retry?: Partial<RetryPolicy>;
  /** Cache TTL in ms (0 = disabled). Only applies to GET. */
  cacheTtlMs?: number;
  /** If true, persist cache to AsyncStorage for cold-start replay. */
  cachePersist?: boolean;
  /** Extra request headers. */
  headers?: Record<string, string>;
  /** Custom abort signal — overrides timeout. */
  signal?: AbortSignal;
  /** Tag used in telemetry & logs. Defaults to URL path. */
  tag?: string;
  /** Query string params. Appended to the URL after merging. */
  params?: Record<string, string | number | boolean | undefined | null>;
}

export interface ApiError extends Error {
  status: number;          // HTTP status (0 if network/abort)
  code: 'network' | 'timeout' | 'abort' | 'http' | 'parse' | 'offline' | 'rate_limited';
  url: string;
  body?: any;              // Parsed error body if available
  requestId?: string;      // X-Request-Id echoed by the server
  retriedTimes: number;    // How many retries we attempted before giving up
}

export interface TelemetrySnapshot {
  totalRequests: number;
  inFlight: number;
  successes: number;
  failures: number;
  retries: number;
  cacheHits: number;
  cacheMisses: number;
  rateLimitedHits: number;
  offlineQueued: number;
  latency: { p50: number; p95: number; max: number };
  lastError?: { tag: string; message: string; at: number };
  byTag: Record<string, { count: number; errors: number; lastLatencyMs: number }>;
}

// ─────────────────────────────────────────────────────────────────────
// INTERNAL STATE
// ─────────────────────────────────────────────────────────────────────
const DEFAULT_RETRY: RetryPolicy = {
  max: 3,
  baseMs: 250,
  capMs: 4000,
  retryStatus: [429, 500, 502, 503, 504],
};

interface Config {
  base: string;
  defaultTimeoutMs: number;
  defaultRetry: RetryPolicy;
  defaultCacheTtlMs: number;
  /** Async hook for adding auth headers per-request. */
  authHook?: () => Promise<Record<string, string>> | Record<string, string>;
  /** When false, controller becomes a passthrough (no cache, no retries). */
  enabled: boolean;
}

const CONFIG: Config = {
  base: API_BASE,
  defaultTimeoutMs: 15_000,
  defaultRetry: { ...DEFAULT_RETRY },
  defaultCacheTtlMs: 0,
  enabled: true,
};

interface CacheEntry { body: any; status: number; expiresAt: number }
const _cache = new Map<string, CacheEntry>();
const _inflight = new Map<string, Promise<any>>();
const _offlineQueue: Array<() => Promise<any>> = [];

const _telemetry: TelemetrySnapshot = {
  totalRequests: 0, inFlight: 0, successes: 0, failures: 0, retries: 0,
  cacheHits: 0, cacheMisses: 0, rateLimitedHits: 0, offlineQueued: 0,
  latency: { p50: 0, p95: 0, max: 0 },
  byTag: {},
};
const _latencies: number[] = []; // ring buffer of last 256

// ─────────────────────────────────────────────────────────────────────
// HELPERS
// ─────────────────────────────────────────────────────────────────────
function _qs(params?: Record<string, any>): string {
  if (!params) return '';
  const sp = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v === undefined || v === null) return;
    sp.set(k, String(v));
  });
  const s = sp.toString();
  return s ? `?${s}` : '';
}

function _absUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) return path;
  const sep = path.startsWith('/') ? '' : '/';
  return CONFIG.base + sep + path;
}

function _percentile(values: number[], pct: number): number {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const idx = Math.max(0, Math.min(sorted.length - 1, Math.floor(pct / 100 * (sorted.length - 1))));
  return Math.round(sorted[idx]);
}

function _recordLatency(ms: number, tag: string, ok: boolean) {
  _latencies.push(ms);
  if (_latencies.length > 256) _latencies.shift();
  _telemetry.latency.p50 = _percentile(_latencies, 50);
  _telemetry.latency.p95 = _percentile(_latencies, 95);
  _telemetry.latency.max = Math.round(Math.max(_telemetry.latency.max, ms));
  const slot = (_telemetry.byTag[tag] ||= { count: 0, errors: 0, lastLatencyMs: 0 });
  slot.count += 1;
  slot.lastLatencyMs = Math.round(ms);
  if (!ok) slot.errors += 1;
}

function _normalizeError(input: any, url: string, retriedTimes: number, requestId?: string): ApiError {
  let err: ApiError;
  if (input && input.name === 'AbortError') {
    err = Object.assign(new Error('Request was aborted') as any, {
      code: 'abort' as const, status: 0, url, retriedTimes, requestId,
    });
  } else if (input && input.code === 'TIMEOUT') {
    err = Object.assign(new Error(`Request timed out`) as any, {
      code: 'timeout' as const, status: 0, url, retriedTimes, requestId,
    });
  } else if (input && typeof input.status === 'number') {
    const code = input.status === 429 ? 'rate_limited' : 'http';
    err = Object.assign(new Error(`HTTP ${input.status} ${input.statusText || ''}`.trim()) as any, {
      code: code as any, status: input.status, url, body: input.body, retriedTimes, requestId,
    });
  } else if (input && typeof input === 'object' && input.message?.includes('Network')) {
    err = Object.assign(new Error(input.message || 'Network error') as any, {
      code: 'network' as const, status: 0, url, retriedTimes, requestId,
    });
  } else {
    err = Object.assign(new Error(input?.message || String(input)) as any, {
      code: 'network' as const, status: 0, url, retriedTimes, requestId,
    });
  }
  _telemetry.lastError = { tag: url, message: err.message, at: Date.now() };
  return err;
}

async function _sleep(ms: number) { return new Promise(r => setTimeout(r, ms)); }

function _backoffWait(attempt: number, policy: RetryPolicy): number {
  const exp = Math.min(policy.capMs, policy.baseMs * Math.pow(2, attempt));
  const jitter = Math.random() * (policy.baseMs / 2);
  return exp + jitter;
}

// ─────────────────────────────────────────────────────────────────────
// CACHE PERSISTENCE (cold-start only — runtime kept in-memory)
// ─────────────────────────────────────────────────────────────────────
const PERSIST_KEY = 'apiController:cache:v1';

async function _persistCache() {
  try {
    const obj: Record<string, CacheEntry> = {};
    _cache.forEach((v, k) => { if (v.expiresAt > Date.now()) obj[k] = v; });
    await AsyncStorage.setItem(PERSIST_KEY, JSON.stringify(obj));
  } catch {}
}
async function _rehydrateCache() {
  try {
    const raw = await AsyncStorage.getItem(PERSIST_KEY);
    if (!raw) return;
    const obj = JSON.parse(raw) as Record<string, CacheEntry>;
    Object.entries(obj).forEach(([k, v]) => {
      if (v.expiresAt > Date.now()) _cache.set(k, v);
    });
  } catch {}
}
_rehydrateCache(); // fire-and-forget at module load

// ─────────────────────────────────────────────────────────────────────
// OFFLINE DETECTION (optional dep — gracefully no-op if missing)
// ─────────────────────────────────────────────────────────────────────
let _isOnline = true;
let _netInfo: any = null;
try {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  _netInfo = require('@react-native-community/netinfo')?.default ?? null;
  if (_netInfo?.addEventListener) {
    _netInfo.addEventListener((state: any) => {
      const wasOnline = _isOnline;
      _isOnline = state?.isConnected !== false;
      if (!wasOnline && _isOnline) _drainOfflineQueue();
    });
  }
} catch { /* NetInfo not installed — treat as always-online */ }

async function _drainOfflineQueue() {
  const drained = _offlineQueue.splice(0);
  for (const fn of drained) {
    try { await fn(); } catch { /* swallow — each request handles its own error */ }
  }
}

// ─────────────────────────────────────────────────────────────────────
// CORE REQUEST
// ─────────────────────────────────────────────────────────────────────
async function _request<T = any>(
  method: string,
  path: string,
  body?: any,
  opts: ApiOptions = {},
): Promise<T> {
  const url = _absUrl(path) + _qs(opts.params);
  const tag = opts.tag || new URL(url, 'http://x').pathname;
  const isGet = method === 'GET' || method === 'HEAD';
  const cacheKey = isGet ? `${method} ${url}` : '';
  const ttl = opts.cacheTtlMs ?? CONFIG.defaultCacheTtlMs;
  const retry = { ...CONFIG.defaultRetry, ...(opts.retry || {}) };
  const timeoutMs = opts.timeoutMs ?? CONFIG.defaultTimeoutMs;

  _telemetry.totalRequests += 1;

  // ── Cache hit ──
  if (isGet && ttl > 0) {
    const hit = _cache.get(cacheKey);
    if (hit && hit.expiresAt > Date.now()) {
      _telemetry.cacheHits += 1;
      return hit.body as T;
    }
    _telemetry.cacheMisses += 1;
  }

  // ── Inflight dedupe (GET only) ──
  if (isGet && _inflight.has(cacheKey)) {
    return _inflight.get(cacheKey) as Promise<T>;
  }

  // ── Build auth + headers ──
  const baseHeaders: Record<string, string> = {
    Accept: 'application/json',
    'X-Client': `expo-${Platform.OS}`,
  };
  if (body !== undefined && !(body instanceof FormData)) {
    baseHeaders['Content-Type'] = 'application/json';
  }
  if (CONFIG.authHook) {
    try {
      const extra = await CONFIG.authHook();
      Object.assign(baseHeaders, extra);
    } catch {}
  }
  Object.assign(baseHeaders, opts.headers || {});

  // ── Offline queue (write requests only) ──
  if (!_isOnline && !isGet) {
    _telemetry.offlineQueued += 1;
    return new Promise<T>((resolve, reject) => {
      _offlineQueue.push(async () => {
        try { resolve(await _request<T>(method, path, body, opts)); }
        catch (e) { reject(e); }
      });
    });
  }

  // ── Attempt loop ──
  const doAttempt = async (): Promise<T> => {
    let attempt = 0;
    let lastErr: ApiError | null = null;
    while (attempt <= retry.max) {
      const controller = new AbortController();
      const signal = opts.signal || controller.signal;
      const timer = setTimeout(() => {
        try { controller.abort((Object.assign(new Error('timeout'), { code: 'TIMEOUT' }))); }
        catch { controller.abort(); }
      }, timeoutMs);
      const t0 = Date.now();
      let requestId: string | undefined;
      try {
        if (CONFIG.enabled === false) {
          // Passthrough mode — just do a vanilla fetch.
          const res = await _internalFetch(url, {
            method, headers: baseHeaders,
            body: body == null ? undefined : body instanceof FormData ? body : JSON.stringify(body),
            signal,
          });
          clearTimeout(timer);
          const parsed = await _parseResponse(res);
          if (!res.ok) throw { status: res.status, statusText: res.statusText, body: parsed };
          return parsed as T;
        }
        const res = await _internalFetch(url, {
          method,
          headers: baseHeaders,
          body: body == null ? undefined : body instanceof FormData ? body : JSON.stringify(body),
          signal,
        });
        clearTimeout(timer);
        requestId = res.headers.get('x-request-id') || undefined;
        const ms = Date.now() - t0;
        const parsed = await _parseResponse(res);
        if (!res.ok) {
          // Retryable status?
          if (retry.retryStatus.includes(res.status) && attempt < retry.max) {
            _telemetry.retries += 1;
            if (res.status === 429) _telemetry.rateLimitedHits += 1;
            attempt += 1;
            await _sleep(_backoffWait(attempt, retry));
            continue;
          }
          _telemetry.failures += 1;
          _recordLatency(ms, tag, false);
          throw _normalizeError({ status: res.status, statusText: res.statusText, body: parsed }, url, attempt, requestId);
        }
        _telemetry.successes += 1;
        _recordLatency(ms, tag, true);
        // ── Cache write ──
        if (isGet && ttl > 0) {
          _cache.set(cacheKey, { body: parsed, status: res.status, expiresAt: Date.now() + ttl });
          if (opts.cachePersist) _persistCache();
        }
        return parsed as T;
      } catch (e: any) {
        clearTimeout(timer);
        const isAbort = e?.name === 'AbortError' || e?.code === 'TIMEOUT';
        const isNetwork = !e?.status && !isAbort;
        // Network / timeout → retry (if budget remains)
        if ((isNetwork || isAbort) && attempt < retry.max) {
          _telemetry.retries += 1;
          attempt += 1;
          await _sleep(_backoffWait(attempt, retry));
          continue;
        }
        _telemetry.failures += 1;
        lastErr = _normalizeError(e, url, attempt, requestId);
        throw lastErr;
      }
    }
    if (lastErr) throw lastErr;
    throw _normalizeError(new Error('exhausted retries'), url, attempt);
  };

  // ── Register inflight (GET) ──
  const promise = (async () => {
    _telemetry.inFlight += 1;
    await _acquireFetchSlot();
    try { return await doAttempt(); }
    finally {
      _releaseFetchSlot();
      _telemetry.inFlight = Math.max(0, _telemetry.inFlight - 1);
      if (isGet) _inflight.delete(cacheKey);
    }
  })();
  if (isGet) _inflight.set(cacheKey, promise);
  return promise as Promise<T>;
}

async function _parseResponse(res: Response): Promise<any> {
  const ct = res.headers.get('content-type') || '';
  if (ct.includes('application/json')) {
    try { return await res.json(); } catch { return null; }
  }
  try { return await res.text(); } catch { return null; }
}

// Internal fetch — prefers the original `fetch` reference stashed by the
// fetchInterceptor (avoids infinite recursion when the interceptor patches
// global fetch and apiController is called via it).
function _internalFetch(input: any, init?: RequestInit): Promise<Response> {
  const g: any = (typeof globalThis !== 'undefined' ? globalThis : (global as any));
  const f = g.__origFetch || g.fetch;
  return f(input, init);
}

// ─────────────────────────────────────────────────────────────────────
// PUBLIC API
// ─────────────────────────────────────────────────────────────────────
export const api = {
  get:    <T = any>(path: string, opts?: ApiOptions) => _request<T>('GET', path, undefined, opts),
  post:   <T = any>(path: string, body?: any, opts?: ApiOptions) => _request<T>('POST', path, body, opts),
  put:    <T = any>(path: string, body?: any, opts?: ApiOptions) => _request<T>('PUT', path, body, opts),
  patch:  <T = any>(path: string, body?: any, opts?: ApiOptions) => _request<T>('PATCH', path, body, opts),
  delete: <T = any>(path: string, opts?: ApiOptions) => _request<T>('DELETE', path, undefined, opts),

  /** Apply runtime config — call once at app start. */
  configure(patch: Partial<Config>) {
    Object.assign(CONFIG, patch);
    if (patch.defaultRetry) CONFIG.defaultRetry = { ...DEFAULT_RETRY, ...patch.defaultRetry };
  },
  /** Live snapshot for the /settings/api panel. */
  getTelemetry(): TelemetrySnapshot { return { ..._telemetry, byTag: { ..._telemetry.byTag } }; },
  /** Drop all in-memory cache. */
  clearCache(): number {
    const n = _cache.size; _cache.clear(); AsyncStorage.removeItem(PERSIST_KEY).catch(() => {}); return n;
  },
  /** Number of cached entries currently held. */
  cacheSize(): number { return _cache.size; },
  /** Force-trigger the offline-queue drain (mostly for tests). */
  drainQueue() { return _drainOfflineQueue(); },
  /** Inspect runtime state — useful in the settings panel. */
  inspect() {
    return {
      base: CONFIG.base,
      enabled: CONFIG.enabled,
      defaultTimeoutMs: CONFIG.defaultTimeoutMs,
      defaultRetry: { ...CONFIG.defaultRetry },
      defaultCacheTtlMs: CONFIG.defaultCacheTtlMs,
      cacheSize: _cache.size,
      inflight: _inflight.size,
      isOnline: _isOnline,
      offlineQueueDepth: _offlineQueue.length,
    };
  },
};

// ─────────────────────────────────────────────────────────────────────
// SOTA drop-in fetch — preserves full `Response` semantics.
// True drop-in for `fetch()`. Adds:
//   • Per-request timeout via AbortController (default 20s)
//   • Telemetry: count, latency, error count, lastError
//   • X-Request-Id tagging in telemetry per-tag
//   • Optional retry: pass init.retry = true (or { max, baseMs }) to enable
//     exponential-backoff retries on network failure / 5xx / 429.
// Response, .status, .ok, .headers, .text(), .json(), .blob() all preserved.
// ─────────────────────────────────────────────────────────────────────
export interface FetchExtras {
  /** Override timeout (ms). Default 20_000. */
  timeoutMs?: number;
  /** Telemetry tag. Defaults to pathname. */
  tag?: string;
  /** Enable retries on 5xx/429/network. */
  retry?: boolean | Partial<RetryPolicy>;
}

// ── Global concurrency cap ─────────────────────────────────────────────
// Hard ceiling on simultaneous in-flight fetches. On low-RAM devices a burst
// of parallel requests (each buffering a JSON/text body) is a reliable OOM
// trigger; this serialises everything beyond MAX_CONCURRENT_FETCHES so the
// network never overruns the JS heap. Excess calls queue (FIFO) and run as
// slots free up.
const MAX_CONCURRENT_FETCHES = 6;
let _activeFetches = 0;
const _fetchWaiters: (() => void)[] = [];
function _acquireFetchSlot(): Promise<void> {
  if (_activeFetches < MAX_CONCURRENT_FETCHES) { _activeFetches += 1; return Promise.resolve(); }
  return new Promise<void>(resolve => { _fetchWaiters.push(() => { _activeFetches += 1; resolve(); }); });
}
function _releaseFetchSlot(): void {
  _activeFetches = Math.max(0, _activeFetches - 1);
  const next = _fetchWaiters.shift();
  if (next) next();
}

export async function apiFetch(
  input: string,
  init?: (RequestInit & FetchExtras) | undefined,
): Promise<Response> {
  const url = _absUrl(input);
  const tag = init?.tag || (() => { try { return new URL(url, 'http://x').pathname; } catch { return url; } })();
  const timeoutMs = init?.timeoutMs ?? 20_000;
  const wantRetry = init?.retry === true || (init?.retry && typeof init.retry === 'object');
  const retryPolicy: RetryPolicy = wantRetry
    ? { ...CONFIG.defaultRetry, ...(typeof init?.retry === 'object' ? init!.retry : {}) }
    : { max: 0, baseMs: 0, capMs: 0, retryStatus: [] };

  // Strip our extras from the init we pass to the real fetch.
  const { timeoutMs: _t, tag: _tg, retry: _r, ...passThru } = (init || {}) as any;

  _telemetry.totalRequests += 1;
  _telemetry.inFlight += 1;

  await _acquireFetchSlot();
  let attempt = 0;
  let lastErr: any = null;
  try {
    while (true) {
      const controller = new AbortController();
      const signal = (passThru as any).signal || controller.signal;
      const timer = setTimeout(() => {
        try { controller.abort((Object.assign(new Error('timeout'), { code: 'TIMEOUT' }))); }
        catch { controller.abort(); }
      }, timeoutMs);
      const t0 = Date.now();
      try {
        const res = await _internalFetch(url, { ...passThru, signal });
        clearTimeout(timer);
        const ms = Date.now() - t0;

        // Retry on transient 5xx/429 (only if retry enabled)
        if (wantRetry && retryPolicy.retryStatus.includes(res.status) && attempt < retryPolicy.max) {
          _telemetry.retries += 1;
          if (res.status === 429) _telemetry.rateLimitedHits += 1;
          attempt += 1;
          await _sleep(_backoffWait(attempt, retryPolicy));
          continue;
        }
        if (res.ok) _telemetry.successes += 1; else _telemetry.failures += 1;
        _recordLatency(ms, tag, res.ok);
        return res;
      } catch (e: any) {
        clearTimeout(timer);
        const isAbort = e?.name === 'AbortError' || e?.code === 'TIMEOUT';
        // Network/timeout error → optionally retry
        if (wantRetry && attempt < retryPolicy.max) {
          _telemetry.retries += 1;
          attempt += 1;
          await _sleep(_backoffWait(attempt, retryPolicy));
          continue;
        }
        _telemetry.failures += 1;
        _telemetry.lastError = { tag, message: e?.message || String(e), at: Date.now() };
        _recordLatency(Date.now() - t0, tag, false);
        lastErr = isAbort
          ? Object.assign(new Error('Request timed out'), { code: 'timeout', status: 0, url })
          : Object.assign(new Error(e?.message || 'Network error'), { code: 'network', status: 0, url });
        throw lastErr;
      }
    }
  } finally {
    _telemetry.inFlight = Math.max(0, _telemetry.inFlight - 1);
    _releaseFetchSlot();
  }
}

export default api;

/**
 * apiController — SOTA frontend HTTP layer.
 *
 *   • Single source of truth for all backend calls.
 *   • Per-request timeout via AbortController.
 *   • Exponential-backoff retries with jitter on 5xx / network errors.
 *   • Request deduplication — identical GET in flight returns the same promise.
 *   • Account-scoped in-memory response cache.
 *   • Offline detection (NetInfo) without deferred mutation replay.
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
import { prepareApiRequest, subscribeApiSessionChanges } from './apiClient';

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
  /** Retained for compatibility; account responses are never persisted. */
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
const _offlineQueue: (() => Promise<any>)[] = [];

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

function _assertCurrent(current: () => boolean): void {
  if (!current()) throw Object.assign(new Error('Account observation detached'), { name: 'AbortError' });
}

async function _sleep(ms: number, signal?: AbortSignal) {
  if (signal?.aborted) throw Object.assign(new Error('Request aborted'), { name: 'AbortError' });
  return new Promise<void>((resolve, reject) => {
    const abort = () => { clearTimeout(timer); signal?.removeEventListener('abort', abort); reject(Object.assign(new Error('Request aborted'), { name: 'AbortError' })); };
    const timer = setTimeout(() => { signal?.removeEventListener('abort', abort); resolve(); }, ms);
    signal?.addEventListener('abort', abort, { once: true });
  });
}

function _backoffWait(attempt: number, policy: RetryPolicy): number {
  const exp = Math.min(policy.capMs, policy.baseMs * Math.pow(2, attempt));
  const jitter = Math.random() * (policy.baseMs / 2);
  return exp + jitter;
}

// ─────────────────────────────────────────────────────────────────────
// CACHE PERSISTENCE (cold-start only — runtime kept in-memory)
// ─────────────────────────────────────────────────────────────────────
const PERSIST_KEY = 'apiController:cache:v1';

// Account responses stay in memory. Legacy cold-start rows had no identity
// boundary and must never be rehydrated after a sign-in or account switch.
void AsyncStorage.removeItem(PERSIST_KEY).catch(() => {});
subscribeApiSessionChanges(() => {
  _cache.clear();
  _inflight.clear();
});

// ─────────────────────────────────────────────────────────────────────
// OFFLINE DETECTION (optional dep — gracefully no-op if missing)
// ─────────────────────────────────────────────────────────────────────
let _isOnline = true;
let _netInfo: any = null;
try {
  // Optional native module is synchronously detected at runtime.
  // eslint-disable-next-line @typescript-eslint/no-require-imports
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
  const ttl = opts.cacheTtlMs ?? CONFIG.defaultCacheTtlMs;
  const retry = { ...CONFIG.defaultRetry, ...(opts.retry || {}) };
  if (!isGet) retry.max = 0; // No declared server-side mutation replay contract.
  const timeoutMs = opts.timeoutMs ?? CONFIG.defaultTimeoutMs;
  const baseHeaders: Record<string, string> = { Accept: 'application/json', 'X-Client': `expo-${Platform.OS}` };
  if (body !== undefined && !(body instanceof FormData)) baseHeaders['Content-Type'] = 'application/json';
  if (CONFIG.authHook) { try { Object.assign(baseHeaders, await CONFIG.authHook()); } catch {} }
  Object.assign(baseHeaders, opts.headers || {});
  const session = await prepareApiRequest(url, baseHeaders, opts.signal);
  const cacheKey = `${session.cacheNamespace}:${method} ${url}`;
  const shareRead = isGet && !opts.signal && !CONFIG.authHook && !Object.keys(opts.headers || {}).length;
  _telemetry.totalRequests += 1;
  try {
    _assertCurrent(session.current);
    if (shareRead && ttl > 0) {
      const hit = _cache.get(cacheKey);
      if (hit && hit.expiresAt > Date.now()) {
        _telemetry.cacheHits += 1;
        return hit.body as T;
      }
      _telemetry.cacheMisses += 1;
    }
    if (shareRead && _inflight.has(cacheKey)) {
      const value = await _inflight.get(cacheKey) as T;
      _assertCurrent(session.current);
      return value;
    }
    // A disconnected write is rejected, never replayed under a later account.
    if (!_isOnline && !isGet) throw _normalizeError(new Error('Offline; request was not submitted'), url, 0);

    const doAttempt = async (): Promise<T> => {
      let attempt = 0;
      while (true) {
        _assertCurrent(session.current);
        const controller = new AbortController();
        const abort = () => controller.abort();
        session.signal.addEventListener('abort', abort, { once: true });
        if (session.signal.aborted) abort();
        const timer = setTimeout(abort, timeoutMs);
        const t0 = Date.now();
        let requestId: string | undefined;
        try {
          const res = await _internalFetch(url, {
            method, headers: session.headers,
            body: body == null ? undefined : body instanceof FormData ? body : JSON.stringify(body),
            signal: controller.signal, ...(session.redirect ? { redirect: session.redirect } : {}),
          });
          _assertCurrent(session.current);
          if (controller.signal.aborted) throw Object.assign(new Error('Request timed out'), { code: 'TIMEOUT' });
          requestId = res.headers.get('x-request-id') || undefined;
          const parsed = await _parseResponse(res);
          _assertCurrent(session.current);
          if (controller.signal.aborted) throw Object.assign(new Error('Request timed out'), { code: 'TIMEOUT' });
          if (!res.ok) throw { status: res.status, statusText: res.statusText, body: parsed };
          _telemetry.successes += 1;
          _recordLatency(Date.now() - t0, tag, true);
          if (shareRead && ttl > 0) _cache.set(cacheKey, { body: parsed, status: res.status, expiresAt: Date.now() + ttl });
          return parsed as T;
        } catch (e: any) {
          _assertCurrent(session.current);
          const retryable = e?.status ? retry.retryStatus.includes(e.status) : true;
          if (CONFIG.enabled && retryable && attempt < retry.max) {
            _telemetry.retries += 1;
            if (e?.status === 429) _telemetry.rateLimitedHits += 1;
            attempt += 1;
            await _sleep(_backoffWait(attempt, retry), session.signal);
            continue;
          }
          _telemetry.failures += 1;
          _recordLatency(Date.now() - t0, tag, false);
          throw _normalizeError(e, url, attempt, requestId);
        } finally {
          clearTimeout(timer);
          session.signal.removeEventListener('abort', abort);
        }
      }
    };
    const promise = (async () => {
      _telemetry.inFlight += 1;
      await _acquireFetchSlot();
      try { return await doAttempt(); }
      finally { _releaseFetchSlot(); _telemetry.inFlight = Math.max(0, _telemetry.inFlight - 1); }
    })();
    if (shareRead) _inflight.set(cacheKey, promise);
    try { return await promise; }
    finally { if (_inflight.get(cacheKey) === promise) _inflight.delete(cacheKey); }
  } finally { session.dispose(); }
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
  const method = (init?.method || 'GET').toUpperCase();
  const wantRetry = (method === 'GET' || method === 'HEAD') && (init?.retry === true || (init?.retry && typeof init.retry === 'object'));
  const retryPolicy: RetryPolicy = wantRetry
    ? { ...CONFIG.defaultRetry, ...(typeof init?.retry === 'object' ? init!.retry : {}) }
    : { max: 0, baseMs: 0, capMs: 0, retryStatus: [] };
  const { timeoutMs: _t, tag: _tg, retry: _r, ...passThru } = (init || {}) as any;
  const headers: Record<string, string> = {};
  new Headers(passThru.headers).forEach((value, key) => { headers[key] = value; });
  const session = await prepareApiRequest(url, headers, passThru.signal);
  _telemetry.totalRequests += 1;
  _telemetry.inFlight += 1;
  await _acquireFetchSlot();
  let attempt = 0;
  let responseOwnsSession = false;
  try {
    while (true) {
      _assertCurrent(session.current);
      const controller = new AbortController();
      const abort = () => controller.abort();
      session.signal.addEventListener('abort', abort, { once: true });
      if (session.signal.aborted) abort();
      let readerOwnsAttempt = false;
      let timer: ReturnType<typeof setTimeout>;
      const finish = () => { clearTimeout(timer); session.signal.removeEventListener('abort', abort); session.dispose(); };
      timer = setTimeout(() => { abort(); finish(); }, timeoutMs);
      const t0 = Date.now();
      try {
        const res = await _internalFetch(url, { ...passThru, headers: session.headers, signal: controller.signal,
          ...(session.redirect ? { redirect: session.redirect } : {}) });
        _assertCurrent(session.current);
        if (controller.signal.aborted) throw Object.assign(new Error('Request timed out'), { code: 'TIMEOUT' });
        if (wantRetry && retryPolicy.retryStatus.includes(res.status) && attempt < retryPolicy.max) {
          _telemetry.retries += 1;
          if (res.status === 429) _telemetry.rateLimitedHits += 1;
          attempt += 1;
          await _sleep(_backoffWait(attempt, retryPolicy), session.signal);
          continue;
        }
        if (res.ok) _telemetry.successes += 1; else _telemetry.failures += 1;
        _recordLatency(Date.now() - t0, tag, res.ok);
        // Body readers remain tied to the admitted account even if a fetch
        // adapter ignores abort while completing its response body.
        for (const name of ['arrayBuffer', 'blob', 'formData', 'json', 'text'] as const) {
          if (typeof res[name] !== 'function') continue;
          const read = res[name].bind(res);
          Object.defineProperty(res, name, { configurable: true, value: async () => {
            try {
              _assertCurrent(session.current);
              const value = await read();
              _assertCurrent(session.current);
              if (controller.signal.aborted) throw Object.assign(new Error('Request timed out'), { code: 'TIMEOUT' });
              return value;
            } finally { finish(); }
          } });
        }
        responseOwnsSession = true;
        readerOwnsAttempt = true;
        return res;
      } catch (e: any) {
        _assertCurrent(session.current);
        if (wantRetry && attempt < retryPolicy.max) {
          _telemetry.retries += 1;
          attempt += 1;
          await _sleep(_backoffWait(attempt, retryPolicy), session.signal);
          continue;
        }
        _telemetry.failures += 1;
        _telemetry.lastError = { tag, message: e?.message || String(e), at: Date.now() };
        _recordLatency(Date.now() - t0, tag, false);
        throw _normalizeError(e, url, attempt);
      } finally {
        if (!readerOwnsAttempt) { clearTimeout(timer); session.signal.removeEventListener('abort', abort); }
      }
    }
  } finally {
    if (!responseOwnsSession) session.dispose();
    _telemetry.inFlight = Math.max(0, _telemetry.inFlight - 1);
    _releaseFetchSlot();
  }
}

export default api;

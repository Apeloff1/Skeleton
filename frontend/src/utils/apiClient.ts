/**
 * src/utils/apiClient.ts — Smart API client (Feb 2026, v2 with circuit
 * breaker + breadcrumb integration).
 *
 * Goodies on top of bare fetch():
 *   • Retries (1 retry on 5xx / network error, exponential backoff).
 *   • Abort on unmount via the optional signal argument.
 *   • Per-call timeout (default 15 s), even when a caller signal is supplied.
 *   • Auto X-Request-Id correlation header.
 *   • 304 / ETag honouring (uses sessionStorage cache).
 *   • Per-host CIRCUIT BREAKER — after 5 consecutive failures within
 *     20 s for the same path-prefix, return fast-fail until cool-off.
 *   • BREADCRUMB integration — every error (status ≥ 400 OR network)
 *     is added to the global breadcrumb trail so error reports carry
 *     "what the user did last".
 *
 * This is the app's single TypeScript HTTP transport. The envelope-style
 * `safeFetch`/`safeGetJson` API (formerly utils/safeFetch.ts) lives at the
 * bottom of this module alongside the `api` client. Long-lived SSE reads
 * (`openEventStream`, formerly utils/apiStream.ts) live here too, but they
 * do not enter the request/retry/circuit-breaker path.
 */
import { trail } from './breadcrumbs';
import { API_BASE } from './apiBase';
import { traceStep } from './bootTracer';
import { boundedResponseChars, boundedRetries, boundedTimeoutMs, retryDelayMs, retryableHttpStatus } from './requestRecoveryPolicy';

const BACKEND = API_BASE;

export interface ApiResult<T = any> {
  ok: boolean;
  status: number;
  data: T | null;
  error: string | null;
  rid: string | null;
}

interface RequestOpts {
  signal?: AbortSignal;
  timeoutMs?: number;
  headers?: Record<string, string>;
  retries?: number;
  idempotencyKey?: string;
  cacheKey?: string;
  cacheTtlMs?: number;
  maxResponseChars?: number;
  /** Explicit opt-in only when server-side idempotent replay is verified. */
  serverDedupeVerified?: boolean;
}

function newRid(): string {
  try {
    return (crypto as any)?.randomUUID?.()?.replace(/-/g, '').slice(0, 16) ||
           Math.random().toString(16).slice(2, 18);
  } catch {
    return Math.random().toString(16).slice(2, 18);
  }
}

// ─────────────────────────────────────────────────────────────────────
// Circuit breaker (per path-prefix bucket).
// CLOSED  → all requests allowed; failures accumulate within window.
// OPEN    → all requests fast-fail with `circuit_open` until cool-off.
// HALF    → exactly ONE probe request allowed; success → CLOSED,
//           failure → OPEN (with exponential cool-off, capped).
// ─────────────────────────────────────────────────────────────────────
const CB_FAIL_THRESHOLD = 5;
const CB_WINDOW_MS = 20_000;
const CB_BASE_COOL_OFF_MS = 15_000;
const CB_MAX_COOL_OFF_MS = 120_000;

type CBState = 'closed' | 'open' | 'half_open';
interface CBEntry {
  state: CBState;
  failures: number[];      // timestamps within sliding window
  openUntil: number;       // ms-since-epoch
  probeInFlight: boolean;  // half-open: a probe is already running
  consecutiveOpens: number;// for exponential cool-off
}
const _cb: Map<string, CBEntry> = new Map();

function _cbGet(bucket: string): CBEntry {
  let e = _cb.get(bucket);
  if (!e) {
    e = { state: 'closed', failures: [], openUntil: 0, probeInFlight: false, consecutiveOpens: 0 };
    _cb.set(bucket, e);
  }
  return e;
}

function _cbBucket(path: string): string {
  // Group by first 2 path segments — /api/feature-flags/foo → /api/feature-flags
  const parts = path.split('?')[0].split('/').filter(Boolean);
  return '/' + parts.slice(0, 2).join('/');
}

/** Returns true if the call is allowed to proceed; marks half-open probe in-flight. */
function _cbCheck(bucket: string): { allowed: boolean; isProbe: boolean } {
  const e = _cbGet(bucket);
  const now = Date.now();

  if (e.state === 'open') {
    if (now < e.openUntil) return { allowed: false, isProbe: false };
    // Cool-off elapsed → transition to half_open.
    e.state = 'half_open';
    e.probeInFlight = false;
  }
  if (e.state === 'half_open') {
    if (e.probeInFlight) return { allowed: false, isProbe: false };
    e.probeInFlight = true;
    trail.add('api', `circuit_half_open ${bucket}`, { probe: true }, 'info');
    return { allowed: true, isProbe: true };
  }
  // closed — drain old failures
  const cutoff = now - CB_WINDOW_MS;
  if (e.failures.length) e.failures = e.failures.filter(t => t > cutoff);
  return { allowed: true, isProbe: false };
}

function _cbReleaseProbe(bucket: string, isProbe: boolean) {
  if (!isProbe) return;
  const e = _cb.get(bucket);
  if (e?.state === 'half_open') e.probeInFlight = false;
}

function _cbRecordFail(bucket: string, isProbe: boolean) {
  const e = _cbGet(bucket);
  const now = Date.now();
  if (e.state === 'half_open' && isProbe) {
    // Probe failed → re-open with exponential back-off
    e.probeInFlight = false;
    e.consecutiveOpens = Math.min(e.consecutiveOpens + 1, 4);
    const coolOff = Math.min(
      CB_BASE_COOL_OFF_MS * Math.pow(2, e.consecutiveOpens - 1),
      CB_MAX_COOL_OFF_MS,
    );
    e.state = 'open';
    e.openUntil = now + coolOff;
    e.failures = [];
    trail.add('api', `circuit_reopen ${bucket}`, { for_ms: coolOff, attempt: e.consecutiveOpens }, 'warn');
    return;
  }
  e.failures.push(now);
  if (e.failures.length >= CB_FAIL_THRESHOLD) {
    e.consecutiveOpens = 1;
    e.state = 'open';
    e.openUntil = now + CB_BASE_COOL_OFF_MS;
    e.failures = [];
    trail.add('api', `circuit_open ${bucket}`, { for_ms: CB_BASE_COOL_OFF_MS }, 'warn');
  }
}

function _cbRecordOk(bucket: string, isProbe: boolean) {
  const e = _cb.get(bucket);
  if (!e) return;
  if (e.state === 'half_open' && isProbe) {
    trail.add('api', `circuit_closed ${bucket}`, { recovered: true }, 'info');
  }
  _cb.delete(bucket);
}

/** Test/admin helper — manually clear a circuit (or all). */
export function _circuitBreakerReset(bucket?: string) {
  if (bucket) _cb.delete(bucket); else _cb.clear();
}

// ─────────────────────────────────────────────────────────────────────
function sleepWithAbort(ms: number, signal?: AbortSignal): Promise<boolean> {
  if (signal?.aborted) return Promise.resolve(false);
  return new Promise(resolve => {
    let settled = false;
    const finish = (value: boolean) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      signal?.removeEventListener?.('abort', onAbort);
      resolve(value);
    };
    const onAbort = () => finish(false);
    const timer = setTimeout(() => finish(true), ms);
    signal?.addEventListener?.('abort', onAbort, { once: true });
    if (signal?.aborted) finish(false);
  });
}

/** Bound streamed UTF-8 before joining a document. Native fetch adapters that
 * expose only text() retain their platform buffering; their result is checked
 * before parsing and the caller still owns an absolute headers/body deadline. */
export async function readBoundedResponseText(res: Response, maximum: number): Promise<{ text: string; oversized: boolean }> {
  const limit = boundedResponseChars(maximum);
  const length = res.headers?.get?.('content-length');
  if (length != null && (!/^[0-9]{1,20}$/.test(length) || Number(length) > limit)) {
    try { void res.body?.cancel().catch(() => undefined); } catch {}
    return { text: '', oversized: true };
  }
  if (!res.body || typeof res.body.getReader !== 'function' || typeof TextDecoder === 'undefined') {
    const text = await res.text();
    return text.length > limit ? { text: '', oversized: true } : { text, oversized: false };
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder('utf-8', { fatal: true });
  const parts: string[] = [];
  let size = 0;
  let complete = false;
  try {
    for (;;) {
      const chunk = await reader.read();
      if (chunk.done) { complete = true; break; }
      size += chunk.value.byteLength;
      if (size > limit) return { text: '', oversized: true };
      const text = decoder.decode(chunk.value, { stream: true });
      // Coalesce small chunks so trickling bytes cannot create millions of
      // array entries within an otherwise valid response byte allowance.
      if (parts.length && parts[parts.length - 1].length < 4096) parts[parts.length - 1] += text;
      else parts.push(text);
    }
    parts.push(decoder.decode());
    return { text: parts.join(''), oversized: false };
  } finally {
    if (!complete) { try { void reader.cancel().catch(() => undefined); } catch {} }
    try { reader.releaseLock(); } catch {}
  }
}

async function _doFetch<T>(
  method: string, path: string, body: any, opts: RequestOpts,
): Promise<ApiResult<T>> {
  const url = path.startsWith('http') ? path : `${BACKEND}${path}`;
  const rid = newRid();
  const bucket = _cbBucket(path);
  // Query parameters can carry signed URLs, bearer tokens or opaque IDs.
  const logPath = path.split(/[?#]/, 1)[0].slice(0, 160);
  const maxResponseChars = boundedResponseChars(opts.maxResponseChars);
  if (opts.signal?.aborted) return { ok: false, status: 0, data: null, error: 'aborted', rid };
  // Credential-bearing and queried requests must not reuse an account-blind
  // session cache. Include the actual public endpoint in every eligible key.
  const publicHeaders = Object.keys(opts.headers || {}).every(key => ['accept', 'content-type', 'cache-control'].includes(key.toLowerCase()));
  const cacheKey = method === 'GET' && opts.cacheKey && publicHeaders && path.startsWith('/') && !/[?#]/.test(url)
    ? `api:${url}:${opts.cacheKey}` : null;

  // Read sessionStorage cache (web only) — a hit needs no network/timer.
  if (cacheKey && typeof sessionStorage !== 'undefined') {
    try {
      const raw = sessionStorage.getItem(cacheKey);
      if (raw && raw.length <= maxResponseChars + 2048) {
        const c = JSON.parse(raw);
        const age = Date.now() - c.ts;
        if (typeof c.ts === 'number' && Number.isFinite(c.ts) && age >= 0 && age < (opts.cacheTtlMs ?? 60_000)) {
          return { ok: true, status: 200, data: c.data, error: null, rid: c.rid || null };
        }
      }
    } catch {}
  }

  // Only a network operation may acquire the half-open probe lease.
  // Cache hits must never strand the circuit in an un-releasable probe.
  const gate = _cbCheck(bucket);
  if (!gate.allowed) {
    return { ok: false, status: 0, data: null, error: 'circuit_open', rid };
  }
  const isProbe = gate.isProbe;

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-Request-Id': rid,
    ...(opts.headers || {}),
  };
  if (opts.idempotencyKey) headers['Idempotency-Key'] = opts.idempotencyKey;

  // ── ANTI-BLIP RETRY POLICY ────────────────────────────────────────────
  // Transient gateway blips (Cloudflare/ingress 502/503/504), network drops
  // and brief backend unresponsiveness (our OWN timeout firing) are all
  // RETRYABLE — they self-heal within a few seconds. Only safe reads and
  // explicitly keyed writes are replayable. Each attempt gets a FRESH abort
  // timer so a hung retry can't outlive its budget, and back-off carries
  // jitter to avoid a thundering herd when the backend recovers.
  const GATEWAY = new Set([502, 503, 504]);
  // Unkeyed writes, including DELETE, are never replayed automatically.
  // Do not let caller-supplied retries/timeout create an unbounded loop.
  const maxAttempts = 1 + boundedRetries(opts.retries, method, !!opts.idempotencyKey, opts.serverDedupeVerified === true);
  const perAttemptTimeout = boundedTimeoutMs(opts.timeoutMs ?? 15_000);

  const backoff = (attempt: number, gateway: boolean) => {
    const base = gateway ? 400 : 200;
    return Math.min(base * Math.pow(2, attempt), 4_000) + Math.floor(Math.random() * 150);
  };

  let lastStatus = 0;
  let lastTimedOut = false;

  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    if (opts.signal?.aborted) {
      _cbReleaseProbe(bucket, isProbe);
      return { ok: false, status: 0, data: null, error: 'aborted', rid };
    }

    // Always own an attempt-level controller so our timeout still works when
    // the caller also supplied a cancellation signal. Forward caller aborts
    // into this controller rather than choosing one signal or the other.
    const ac = typeof AbortController !== 'undefined' ? new AbortController() : null;
    let callerAborted = false;
    let rejectCancelled: (error: Error) => void = () => {};
    const cancelled = new Promise<never>((_resolve, reject) => { rejectCancelled = reject; });
    const abortFromCaller = () => {
      callerAborted = true;
      try { ac?.abort(); } catch {}
      rejectCancelled(new Error('request_cancelled'));
    };
    if (opts.signal) opts.signal.addEventListener('abort', abortFromCaller, { once: true });
    if (opts.signal?.aborted) abortFromCaller();
    const signal = ac?.signal || opts.signal;
    let timedOut = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    // The deadline races the entire headers+body operation; AbortController
    // alone does not guarantee a bounded wait on all native fetch adapters.
    const deadline = new Promise<never>((_resolve, reject) => {
      timer = setTimeout(() => {
        timedOut = true;
        try { ac?.abort(); } catch {}
        reject(new Error('request_timeout'));
      }, perAttemptTimeout);
    });
    const cleanup = () => {
      if (timer !== null) clearTimeout(timer);
      if (opts.signal) opts.signal.removeEventListener('abort', abortFromCaller);
    };

    try {
      const { res, text, oversized } = await Promise.race([
        (async () => {
          const res = await fetch(url, {
            method, headers, signal,
            body: body == null ? undefined : JSON.stringify(body),
          });
          const bounded = await readBoundedResponseText(res, maxResponseChars);
          if (bounded.oversized) ac?.abort();
          return { res, ...bounded };
        })(),
        deadline,
        cancelled,
      ]);
      cleanup();
      if (oversized) {
        _cbReleaseProbe(bucket, isProbe);
        return { ok: false, status: res.status, data: null, error: 'response_too_large', rid };
      }

      // If cancellation raced a completed fetch/body read, cancellation wins:
      // callers that have left the screen should never receive stale success.
      if (callerAborted || opts.signal?.aborted) {
        _cbReleaseProbe(bucket, isProbe);
        return { ok: false, status: 0, data: null, error: 'aborted', rid };
      }

      let data: any = null;
      try { data = text ? JSON.parse(text) : null; } catch { data = text; }

      const transient = retryableHttpStatus(res.status);
      if (!res.ok && transient && attempt < maxAttempts - 1) {
        lastStatus = res.status;
        trail.add('api', `${method} ${logPath} → ${res.status} (retry ${attempt + 1}/${maxAttempts - 1})`,
          { rid, gateway: GATEWAY.has(res.status) }, 'warn');
        if (!(await sleepWithAbort(backoff(attempt, GATEWAY.has(res.status)), opts.signal))) {
          _cbReleaseProbe(bucket, isProbe);
          return { ok: false, status: 0, data: null, error: 'aborted', rid };
        }
        continue;
      }

      if (res.ok && cacheKey && typeof sessionStorage !== 'undefined') {
        try { sessionStorage.setItem(cacheKey, JSON.stringify({ ts: Date.now(), data, rid })); } catch {}
      }

      if (!res.ok) {
        if (transient) _cbRecordFail(bucket, isProbe);
        else _cbRecordOk(bucket, isProbe); // 4xx proves the transport is reachable
        trail.add('api', `${method} ${logPath} → ${res.status}`,
          { rid, error: `HTTP ${res.status}` },
          res.status >= 500 ? 'error' : 'warn',
        );
      } else {
        _cbRecordOk(bucket, isProbe);
      }

      return {
        ok: res.ok, status: res.status, data,
        error: res.ok ? null : (typeof data === 'object' ? data?.error || data?.detail : String(data)) || `HTTP ${res.status}`,
        rid: res.headers.get('x-request-id') || rid,
      };
    } catch {
      cleanup();
      lastTimedOut = timedOut;

      // Caller cancellation is intentional. It must neither retry nor poison
      // the circuit breaker. A half-open probe is released for the next caller.
      const userAbort = callerAborted || (!!opts.signal?.aborted && !timedOut);
      if (userAbort) {
        _cbReleaseProbe(bucket, isProbe);
        return { ok: false, status: 0, data: null, error: 'aborted', rid };
      }

      // Our own timeout or a network error is a transient blip: retry while
      // attempts remain, preserving the same request id for correlation.
      if (attempt < maxAttempts - 1) {
        trail.add('api', `${method} ${logPath} ${timedOut ? 'timeout' : 'network_error'} (retry ${attempt + 1}/${maxAttempts - 1})`,
          { rid }, 'warn');
        if (!(await sleepWithAbort(backoff(attempt, true), opts.signal))) {
          _cbReleaseProbe(bucket, isProbe);
          return { ok: false, status: 0, data: null, error: 'aborted', rid };
        }
        continue;
      }
    }
  }
  _cbRecordFail(bucket, isProbe);
  // A native fetch exception can echo auth headers or the full signed URL.
  // Surface a typed error rather than propagating untrusted exception text.
  const finalError = lastTimedOut ? 'timeout' : (lastStatus ? `HTTP ${lastStatus}` : 'network_error');
  trail.add('api', `${method} ${logPath} failed_after_retries`,
    { rid, lastStatus, error: finalError }, 'error');
  return {
    ok: false, status: lastStatus || 0, data: null,
    error: finalError, rid,
  };
}

const api = {
  get:  <T = any>(path: string, opts: RequestOpts = {}) => _doFetch<T>('GET', path, null, opts),
  post: <T = any>(path: string, body?: any, opts: RequestOpts = {}) => _doFetch<T>('POST', path, body, opts),
  put:  <T = any>(path: string, body?: any, opts: RequestOpts = {}) => _doFetch<T>('PUT', path, body, opts),
  patch: <T = any>(path: string, body?: any, opts: RequestOpts = {}) => _doFetch<T>('PATCH', path, body, opts),
  del:  <T = any>(path: string, opts: RequestOpts = {}) => _doFetch<T>('DELETE', path, null, opts),
  delete: <T = any>(path: string, opts: RequestOpts = {}) => _doFetch<T>('DELETE', path, null, opts),
};

/** Inspector helper — returns the current breaker state (used by /api/health surfaces). */
export function _circuitBreakerStats(): Record<string, { state: CBState; failures: number; openUntil: number; consecutiveOpens: number }> {
  const out: Record<string, { state: CBState; failures: number; openUntil: number; consecutiveOpens: number }> = {};
  _cb.forEach((v, k) => {
    out[k] = {
      state: v.state,
      failures: v.failures.length,
      openUntil: v.openUntil,
      consecutiveOpens: v.consecutiveOpens,
    };
  });
  return out;
}


// ── Envelope transport (formerly utils/safeFetch.ts) ─────────────────────
// Bounded, idempotency-aware JSON transport. A retry cannot duplicate an
// unkeyed mutation; the deadline covers headers AND body. Cancellation and
// excessive responses are reported as envelopes, not throws.

let _offline = false;
export function setOfflineState(offline: boolean) { _offline = offline; }
export function isOffline(): boolean { return _offline; }

export interface FetchEnvelope<T = any> {
  ok: boolean;
  status: number;
  data?: T;
  error?: string;
}

export interface FetchOpts {
  method?: string;
  headers?: Record<string, string>;
  body?: any;
  timeoutMs?: number;
  retries?: number;
  trace?: boolean;
  absolute?: boolean;
  signal?: AbortSignal;
  maxResponseChars?: number;
  /** Only true for endpoints proven to enforce server-side idempotency keys. */
  serverDedupeVerified?: boolean;
}

function resolveUrl(path: string, absolute?: boolean): string {
  if (absolute || /^https?:\/\//i.test(path)) return path;
  if (path.startsWith('/api') && BACKEND) return `${BACKEND}${path}`;
  return path;
}

function redactedPath(path: string): string {
  // Query strings can include auth tickets; never emit them into boot logs.
  return path.split(/[?#]/, 1)[0].slice(0, 100);
}

function recordRetry(path: string, attempt: number, status: number): void {
  try { void traceStep(`safeFetch_retry_${attempt}_status_${status}_${redactedPath(path)}`).catch(() => {}); } catch {}
}

function isAborted(signal?: AbortSignal): boolean {
  return !!signal?.aborted;
}

async function envelopeBackoff(ms: number, signal?: AbortSignal): Promise<boolean> {
  if (isAborted(signal)) return false;
  return new Promise(resolve => {
    let settled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const finish = (ok: boolean) => {
      if (settled) return;
      settled = true;
      if (timer !== null) clearTimeout(timer);
      signal?.removeEventListener?.('abort', onAbort);
      resolve(ok);
    };
    const onAbort = () => finish(false);
    signal?.addEventListener?.('abort', onAbort, { once: true });
    timer = setTimeout(() => finish(true), ms);
    if (isAborted(signal)) finish(false);
  });
}

async function attemptRequest<T>(
  url: string,
  method: string,
  headers: Record<string, string>,
  body: BodyInit | undefined,
  timeoutMs: number,
  signal?: AbortSignal,
  maxResponseChars = boundedResponseChars(undefined),
): Promise<FetchEnvelope<T>> {
  if (isAborted(signal)) return { ok: false, status: 0, error: 'aborted' };
  const ctrl = new AbortController();
  let timer: ReturnType<typeof setTimeout> | null = null;
  let didTimeout = false;
  let abortResult: (result: FetchEnvelope<T>) => void = () => {};
  const cancelled = new Promise<FetchEnvelope<T>>(resolve => { abortResult = resolve; });
  const onAbort = () => {
    ctrl.abort();
    abortResult({ ok: false, status: 0, error: 'aborted' });
  };
  signal?.addEventListener?.('abort', onAbort, { once: true });
  if (isAborted(signal)) onAbort();

  try {
    // Do not rely solely on AbortController: some React Native adapters may
    // ignore an abort while response.text() is pending.
    const request = (async (): Promise<FetchEnvelope<T>> => {
      const res = await fetch(url, { method, headers, body, signal: ctrl.signal });
      const bounded = await readBoundedResponseText(res, maxResponseChars);
      if (bounded.oversized) { ctrl.abort(); return { ok: false, status: res.status, error: 'response_too_large' }; }
      const raw = bounded.text;
      let parsed: any = undefined;
      if (raw) {
        try { parsed = JSON.parse(raw); } catch { parsed = raw; }
      }
      if (res.ok) return { ok: true, status: res.status, data: parsed as T };
      const detail = typeof parsed === 'string' ? parsed : (parsed?.detail ?? `HTTP ${res.status}`);
      return { ok: false, status: res.status, error: String(detail).slice(0, 250) };
    })();
    const deadline = new Promise<FetchEnvelope<T>>((_, reject) => {
      timer = setTimeout(() => {
        didTimeout = true;
        ctrl.abort();
        reject(new Error('request_timeout'));
      }, timeoutMs);
    });
    // A caller navigating away receives cancellation immediately even if a
    // native fetch adapter ignores AbortController while reading its body.
    return await Promise.race([request, deadline, cancelled]);
  } catch {
    const error = didTimeout ? 'timeout' : isAborted(signal) ? 'aborted' : 'network_error';
    return { ok: false, status: 0, error };
  } finally {
    if (timer !== null) clearTimeout(timer);
    signal?.removeEventListener?.('abort', onAbort);
  }
}

export async function safeFetch<T = any>(path: string, opts: FetchOpts = {}): Promise<FetchEnvelope<T>> {
  const method = (opts.method || 'GET').toUpperCase();
  const timeoutMs = boundedTimeoutMs(opts.timeoutMs);
  const headers: Record<string, string> = { Accept: 'application/json', ...opts.headers };
  const keyed = Object.keys(headers).some(key => key.toLowerCase() === 'idempotency-key' && !!headers[key]);
  const retries = boundedRetries(opts.retries, method, keyed, opts.serverDedupeVerified === true);
  const url = resolveUrl(path, opts.absolute);
  let body: BodyInit | undefined;
  try {
    if (opts.body !== undefined) {
      if (typeof opts.body === 'string') body = opts.body;
      else {
        if (!Object.keys(headers).some(key => key.toLowerCase() === 'content-type')) {
          headers['Content-Type'] = 'application/json';
        }
        body = JSON.stringify(opts.body);
      }
    }
  } catch {
    return { ok: false, status: 0, error: 'invalid_request_body' };
  }

  for (let attempt = 0; attempt <= retries; attempt++) {
    if (isAborted(opts.signal)) return { ok: false, status: 0, error: 'aborted' };
    if (_offline && attempt > 0) return { ok: false, status: 0, error: 'offline' };
    const result = await attemptRequest<T>(url, method, headers, body, timeoutMs, opts.signal, boundedResponseChars(opts.maxResponseChars));
    if (result.ok || result.error === 'aborted' || result.error === 'response_too_large') return result;

    // Only replay safe methods or explicitly server-verified keyed writes.
    if (attempt >= retries || (result.status !== 0 && !retryableHttpStatus(result.status))) return result;
    if (opts.trace !== false) recordRetry(path, attempt + 1, result.status);
    if (!(await envelopeBackoff(retryDelayMs(attempt), opts.signal))) {
      return { ok: false, status: 0, error: 'aborted' };
    }
  }
  return { ok: false, status: 0, error: 'unreachable' };
}

export async function safeGetJson<T = any>(
  path: string,
  opts: Omit<FetchOpts, 'method' | 'body'> = {},
): Promise<FetchEnvelope<T>> {
  return safeFetch<T>(path, { ...opts, method: 'GET' });
}

// ── Streaming transport (SSE, ADR-realtime-transport v1) ─────────────────
// Same API_BASE and the same module as every other app HTTP call. The read
// stays off the retry/circuit-breaker path: a stream is one long response,
// and src/foundation/realtime owns parsing, resume and backoff.
export interface EventStreamOpts {
  headers?: Record<string, string>;
  signal?: AbortSignal;
  onOpen?: (status: number) => void;
  onChunk: (text: string) => void;
}
export type EventStreamEnd =
  | { kind: 'eof' } | { kind: 'aborted' } | { kind: 'http'; status: number } | { kind: 'error'; error: string };

type StreamFetch = (url: string, init: { headers: Record<string, string>; signal?: AbortSignal }) => Promise<{
  ok: boolean; status: number;
  headers?: { get?: (name: string) => string | null };
  body?: { getReader?: () => { read: () => Promise<{ done: boolean; value?: Uint8Array }>; cancel?: () => Promise<void> } } | null;
  text: () => Promise<string>;
}>;

function resolveStreamFetch(): StreamFetch {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const expoFetch = require('expo/fetch')?.fetch;
    if (typeof expoFetch === 'function') return expoFetch as StreamFetch;
  } catch { /* web and tests use global fetch */ }
  return fetch as unknown as StreamFetch;
}

export async function openEventStream(path: string, opts: EventStreamOpts): Promise<EventStreamEnd> {
  const url = /^https?:\/\//i.test(path) ? path : `${BACKEND}${path}`;
  try {
    const res = await resolveStreamFetch()(url, {
      headers: { Accept: 'text/event-stream', 'Cache-Control': 'no-cache', ...opts.headers },
      signal: opts.signal,
    });
    if (!res.ok) return { kind: 'http', status: res.status };
    const contentType = res.headers?.get?.('content-type') ?? '';
    if (contentType && !contentType.toLowerCase().includes('text/event-stream')) {
      return { kind: 'error', error: 'not_event_stream' };
    }
    opts.onOpen?.(res.status);
    const reader = res.body?.getReader?.();
    if (!reader) {
      // No streaming body on this platform: deliver what arrived; caller reconnects.
      opts.onChunk(await res.text());
      return { kind: 'eof' };
    }
    const decoder = new TextDecoder();
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      if (value) opts.onChunk(decoder.decode(value, { stream: true }));
    }
    const tail = decoder.decode();
    if (tail) opts.onChunk(tail);
    return { kind: 'eof' };
  } catch {
    if (opts.signal?.aborted) return { kind: 'aborted' };
    // Never surface raw exception text: it may echo signed URLs or headers.
    return { kind: 'error', error: 'network_error' };
  }
}

export default api;

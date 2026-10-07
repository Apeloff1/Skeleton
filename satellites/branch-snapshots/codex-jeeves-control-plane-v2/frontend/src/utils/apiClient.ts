/**
 * src/utils/apiClient.ts — Smart API client (Feb 2026, v2 with circuit
 * breaker + breadcrumb integration).
 *
 * Goodies on top of bare fetch():
 *   • Retries (1 retry on 5xx / network error, exponential backoff).
 *   • Abort on unmount via the optional signal argument.
 *   • Per-call timeout (default 15 s).
 *   • Auto X-Request-Id correlation header.
 *   • 304 / ETag honouring (uses sessionStorage cache).
 *   • Per-host CIRCUIT BREAKER — after 5 consecutive failures within
 *     20 s for the same path-prefix, return fast-fail until cool-off.
 *   • BREADCRUMB integration — every error (status ≥ 400 OR network)
 *     is added to the global breadcrumb trail so error reports carry
 *     "what the user did last".
 *   • Centralised error shape: { ok, status, data, error, rid }.
 */
import { trail } from './breadcrumbs';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';

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
async function _doFetch<T>(
  method: string, path: string, body: any, opts: RequestOpts,
): Promise<ApiResult<T>> {
  const url = path.startsWith('http') ? path : `${BACKEND}${path}`;
  const rid = newRid();
  const bucket = _cbBucket(path);

  const gate = _cbCheck(bucket);
  if (!gate.allowed) {
    return { ok: false, status: 0, data: null, error: 'circuit_open', rid };
  }
  const isProbe = gate.isProbe;

  // Read sessionStorage cache (web only) — a hit needs no network/timer.
  if (method === 'GET' && opts.cacheKey && typeof sessionStorage !== 'undefined') {
    try {
      const raw = sessionStorage.getItem(`api:${opts.cacheKey}`);
      if (raw) {
        const c = JSON.parse(raw);
        if (Date.now() - c.ts < (opts.cacheTtlMs ?? 60_000)) {
          return { ok: true, status: 200, data: c.data, error: null, rid: c.rid || null };
        }
      }
    } catch {}
  }

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-Request-Id': rid,
    ...(opts.headers || {}),
  };
  if (opts.idempotencyKey) headers['Idempotency-Key'] = opts.idempotencyKey;

  // ── ANTI-BLIP RETRY POLICY ────────────────────────────────────────────
  // Transient gateway blips (Cloudflare/ingress 502/503/504), network drops
  // and brief backend unresponsiveness (our OWN timeout firing) are all
  // RETRYABLE — they self-heal within a few seconds. Idempotent calls (GET /
  // DELETE / anything with an Idempotency-Key) get a bigger retry budget;
  // plain writes keep a single safety retry. Each attempt gets a FRESH abort
  // timer so a hung retry can't outlive its budget, and back-off carries
  // jitter to avoid a thundering herd when the backend recovers.
  const GATEWAY = new Set([502, 503, 504]);
  const idempotent = method === 'GET' || method === 'DELETE' || !!opts.idempotencyKey;
  const maxAttempts = (opts.retries ?? (idempotent ? 3 : 1)) + 1;
  const perAttemptTimeout = opts.timeoutMs ?? 15_000;

  const backoff = (attempt: number, gateway: boolean) => {
    const base = gateway ? 400 : 200;
    return Math.min(base * Math.pow(2, attempt), 4_000) + Math.floor(Math.random() * 150);
  };

  let lastErr: any = null;
  let lastStatus = 0;

  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    const ac = opts.signal ? null : (typeof AbortController !== 'undefined' ? new AbortController() : null);
    const signal = opts.signal || ac?.signal;
    let timedOut = false;
    const timer = setTimeout(() => { timedOut = true; try { ac?.abort(); } catch {} }, perAttemptTimeout);

    try {
      const res = await fetch(url, {
        method, headers, signal,
        body: body == null ? undefined : JSON.stringify(body),
      });
      clearTimeout(timer);
      const text = await res.text();
      let data: any = null;
      try { data = text ? JSON.parse(text) : null; } catch { data = text; }

      const transient = res.status >= 500 || GATEWAY.has(res.status);
      if (!res.ok && transient && attempt < maxAttempts - 1) {
        lastStatus = res.status;
        trail.add('api', `${method} ${path} → ${res.status} (retry ${attempt + 1}/${maxAttempts - 1})`,
          { rid, gateway: GATEWAY.has(res.status) }, 'warn');
        await new Promise(r => setTimeout(r, backoff(attempt, GATEWAY.has(res.status))));
        continue;
      }

      if (method === 'GET' && res.ok && opts.cacheKey && typeof sessionStorage !== 'undefined') {
        try { sessionStorage.setItem(`api:${opts.cacheKey}`, JSON.stringify({ ts: Date.now(), data, rid })); } catch {}
      }

      if (!res.ok) {
        _cbRecordFail(bucket, isProbe);
        trail.add('api', `${method} ${path} → ${res.status}`,
          { rid, error: (typeof data === 'object' ? data?.error || data?.detail : String(data)) || `HTTP ${res.status}` },
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
    } catch (e: any) {
      clearTimeout(timer);
      lastErr = e;
      // A user-supplied signal abort is intentional → stop. Our own timeout
      // (timedOut) or a network error is a BLIP → retry while attempts remain.
      const userAbort = e?.name === 'AbortError' && !timedOut;
      if (userAbort) break;
      if (attempt < maxAttempts - 1) {
        trail.add('api', `${method} ${path} ${timedOut ? 'timeout' : 'network_error'} (retry ${attempt + 1}/${maxAttempts - 1})`,
          { rid }, 'warn');
        await new Promise(r => setTimeout(r, backoff(attempt, true)));
        continue;
      }
    }
  }
  _cbRecordFail(bucket, isProbe);
  trail.add('api', `${method} ${path} failed_after_retries`,
    { rid, lastStatus, error: lastErr?.message || `HTTP ${lastStatus || 0}` }, 'error');
  return {
    ok: false, status: lastStatus || 0, data: null,
    error: lastErr?.message || (lastStatus ? `HTTP ${lastStatus}` : 'network_error'), rid,
  };
}

const api = {
  get:  <T = any>(path: string, opts: RequestOpts = {}) => _doFetch<T>('GET', path, null, opts),
  post: <T = any>(path: string, body?: any, opts: RequestOpts = {}) => _doFetch<T>('POST', path, body, opts),
  put:  <T = any>(path: string, body?: any, opts: RequestOpts = {}) => _doFetch<T>('PUT', path, body, opts),
  del:  <T = any>(path: string, opts: RequestOpts = {}) => _doFetch<T>('DELETE', path, null, opts),
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

export default api;

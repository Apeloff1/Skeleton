/**
 * Bounded, idempotency-aware JSON transport.
 *
 * A retry cannot duplicate an unkeyed mutation. The deadline covers both
 * headers AND body, including fetch adapters that ignore AbortController.
 * Cancellation and excessive responses are reported as envelopes, not throws.
 */
import { traceStep } from './bootTracer';
import { API_BASE } from './apiBase';
import { boundedResponseChars, boundedRetries, boundedTimeoutMs, retryDelayMs, retryableHttpStatus } from './requestRecoveryPolicy';

const BACKEND = API_BASE;

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

async function backoff(ms: number, signal?: AbortSignal): Promise<boolean> {
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
  const onAbort = () => ctrl.abort();
  signal?.addEventListener?.('abort', onAbort, { once: true });

  try {
    // Do not rely solely on AbortController: some React Native adapters may
    // ignore an abort while response.text() is pending.
    const request = (async (): Promise<FetchEnvelope<T>> => {
      const res = await fetch(url, { method, headers, body, signal: ctrl.signal });
      const length = Number(res.headers?.get?.('content-length') || 0);
      if (length > maxResponseChars) return { ok: false, status: res.status, error: 'response_too_large' };
      const raw = await res.text();
      if (raw.length > maxResponseChars) return { ok: false, status: res.status, error: 'response_too_large' };
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
    return await Promise.race([request, deadline]);
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

    // Only replay safe/idempotency-keyed methods, and only transient errors.
    if (attempt >= retries || (result.status !== 0 && !retryableHttpStatus(result.status))) return result;
    if (opts.trace !== false) recordRetry(path, attempt + 1, result.status);
    if (!(await backoff(retryDelayMs(attempt), opts.signal))) {
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

/**
 * safeFetch — defensive wrapper around `fetch` with:
 *
 *   • A hard request timeout (AbortController) — default 12s.
 *   • Exponential-backoff retries on network errors and 5xx (default 2 retries).
 *   • Automatic JSON parsing with try/catch (no surprise SyntaxErrors).
 *   • Always returns an envelope: { ok, status, data?, error? } — never throws.
 *   • Emits trace steps so the boot tracer / safe-mode UI can show
 *     in-flight network failures.
 *
 * Usage:
 *   const res = await safeFetch<{items: Foo[]}>('/api/foo');
 *   if (res.ok) use(res.data); else showError(res.error);
 */
import { traceStep } from './bootTracer';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';

// ── Offline state (wired by OfflineBanner / useNetworkStatus) ───────
// When set to true, in-flight retries bail early instead of running
// the full exponential backoff against a dead network.
let _offline = false;
export function setOfflineState(offline: boolean) { _offline = offline; }
export function isOffline(): boolean { return _offline; }

export interface FetchEnvelope<T = any> {
  ok:     boolean;
  status: number;
  data?:  T;
  error?: string;
}

export interface FetchOpts {
  method?:  string;
  headers?: Record<string, string>;
  body?:    any;
  /** Override default 12s timeout. */
  timeoutMs?: number;
  /** Override default 2 retries. */
  retries?: number;
  /** When true, log the failure to bootTracer (default true). */
  trace?: boolean;
  /** Prepend EXPO_PUBLIC_BACKEND_URL if the path starts with /api. */
  absolute?: boolean;
}

function _backoff(attempt: number): number {
  return Math.min(8000, 400 * Math.pow(2, attempt));
}

function _resolveUrl(path: string, absolute?: boolean): string {
  if (absolute) return path;
  if (path.startsWith('http')) return path;
  if (path.startsWith('/api') && BACKEND) return `${BACKEND}${path}`;
  return path;
}

export async function safeFetch<T = any>(path: string, opts: FetchOpts = {}): Promise<FetchEnvelope<T>> {
  const url      = _resolveUrl(path, opts.absolute);
  const method   = opts.method ?? 'GET';
  const timeout  = opts.timeoutMs ?? 12000;
  const retries  = Math.max(0, opts.retries ?? 2);
  const headers: Record<string, string> = {
    'Accept': 'application/json',
    ...(opts.headers || {}),
  };
  let body: BodyInit | undefined;
  if (opts.body !== undefined) {
    if (typeof opts.body === 'string') body = opts.body;
    else {
      headers['Content-Type'] = headers['Content-Type'] || 'application/json';
      body = JSON.stringify(opts.body);
    }
  }

  for (let attempt = 0; attempt <= retries; attempt++) {
    // Skip retries when we're known to be offline — the network call
    // will fail in ~30s anyway, no point waiting.
    if (_offline && attempt > 0) {
      return { ok: false, status: 0, error: 'offline' };
    }
    const ctrl = new AbortController();
    const t    = setTimeout(() => ctrl.abort(), timeout);
    try {
      const res = await fetch(url, { method, headers, body, signal: ctrl.signal });
      clearTimeout(t);
      let parsed: any = undefined;
      const text = await res.text();
      if (text) {
        try { parsed = JSON.parse(text); }
        catch { parsed = text; }
      }
      if (res.ok) return { ok: true, status: res.status, data: parsed as T };
      // 5xx are retryable; 4xx are not.
      if (res.status >= 500 && attempt < retries) {
        if (opts.trace !== false) traceStep(`safeFetch retry ${attempt + 1}/${retries} ${res.status} ${path}`).catch(() => {});
        await new Promise(r => setTimeout(r, _backoff(attempt)));
        continue;
      }
      return { ok: false, status: res.status, error: typeof parsed === 'string' ? parsed : (parsed?.detail || `HTTP ${res.status}`) };
    } catch (e: any) {
      clearTimeout(t);
      const msg = e?.message || String(e);
      if (attempt < retries) {
        if (opts.trace !== false) traceStep(`safeFetch retry ${attempt + 1}/${retries} err ${path}: ${msg.slice(0,40)}`).catch(() => {});
        await new Promise(r => setTimeout(r, _backoff(attempt)));
        continue;
      }
      return { ok: false, status: 0, error: msg };
    }
  }
  // Unreachable but TypeScript needs it.
  return { ok: false, status: 0, error: 'unreachable' };
}

/** Convenience GET. */
export async function safeGetJson<T = any>(path: string, opts: Omit<FetchOpts, 'method' | 'body'> = {}): Promise<FetchEnvelope<T>> {
  return safeFetch<T>(path, { ...opts, method: 'GET' });
}

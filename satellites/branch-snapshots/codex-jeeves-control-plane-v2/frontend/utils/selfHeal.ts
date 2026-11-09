/**
 * selfHeal — exponential-backoff retry + auto-recovery helpers.
 *
 *   const data = await withRetry(() => fetch('/api/whatever').then(r => r.json()), {
 *     attempts: 4, baseMs: 250, label: 'whatever',
 *   });
 *
 * Also exposes useBackendHealth() for showing a self-heal banner.
 */
import { useEffect, useState } from 'react';
import { recordEvent } from './modalLogger';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';

export interface RetryOpts {
  attempts?: number;     // default 4
  baseMs?:   number;     // default 200
  maxMs?:    number;     // cap; default 4000
  label?:    string;     // for telemetry
  shouldRetry?: (err: any) => boolean;
}

export async function withRetry<T>(fn: () => Promise<T>, opts: RetryOpts = {}): Promise<T> {
  const attempts = opts.attempts ?? 4;
  const baseMs   = opts.baseMs   ?? 200;
  const maxMs    = opts.maxMs    ?? 4000;
  const should   = opts.shouldRetry ?? (() => true);
  let lastErr: any = null;
  for (let i = 0; i < attempts; i++) {
    try {
      return await fn();
    } catch (e) {
      lastErr = e;
      if (i === attempts - 1 || !should(e)) break;
      const delay = Math.min(maxMs, baseMs * 2 ** i) + Math.random() * 100;
      if (opts.label) {
        recordEvent('__selfheal__', `retry:${opts.label}`, 'warn', { attempt: i + 1, delay_ms: Math.round(delay), err: String(e).slice(0, 200) });
      }
      await new Promise(r => setTimeout(r, delay));
    }
  }
  if (opts.label) {
    recordEvent('__selfheal__', `give_up:${opts.label}`, 'error', { err: String(lastErr).slice(0, 400) });
  }
  throw lastErr;
}

export interface HealthSnapshot {
  ok: boolean;
  error_rate: number;
  ts: number;
  online: boolean;
}

export function useBackendHealth(intervalMs: number = 30_000): HealthSnapshot {
  const [snap, setSnap] = useState<HealthSnapshot>({ ok: true, error_rate: 0, ts: 0, online: true });
  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const r = await fetch(`${BACKEND}/api/security/health`, { method: 'GET' });
        const j = await r.json();
        if (!cancelled) setSnap({ ok: !!j.ok, error_rate: j.error_rate || 0, ts: j.ts || Date.now() / 1000, online: true });
      } catch {
        if (!cancelled) setSnap(s => ({ ...s, online: false, ok: false }));
      }
    };
    tick();
    const id = setInterval(tick, intervalMs);
    return () => { cancelled = true; clearInterval(id); };
  }, [intervalMs]);
  return snap;
}

export async function fetchJSON<T = any>(url: string, init?: RequestInit, opts?: RetryOpts): Promise<T> {
  return withRetry(async () => {
    const r = await fetch(url, init);
    if (!r.ok) throw new Error(`HTTP ${r.status} ${url}`);
    return r.json();
  }, { label: opts?.label || url.split('?')[0].slice(-40), ...opts });
}

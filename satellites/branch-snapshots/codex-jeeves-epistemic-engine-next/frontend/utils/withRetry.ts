/**
 * withRetry — generic exponential-backoff retry helper for any async op.
 *
 *   const result = await withRetry(
 *     async () => myFlakyOperation(),
 *     { retries: 3, baseMs: 400, factor: 2, maxMs: 8000, retryOn: (e) => true }
 *   );
 *
 * Returns { ok: true, value }  | { ok: false, error, attempts }.
 * Never throws.
 *
 * `retryOn` can short-circuit retries for known-fatal errors (e.g. 4xx).
 */
import { recordEvent } from './modalLogger';

export interface RetryOpts<T> {
  retries?:   number;        // default 2
  baseMs?:    number;        // default 400
  factor?:    number;        // default 2
  maxMs?:     number;        // default 8000
  retryOn?:   (err: any) => boolean;  // default true
  /** Optional name for telemetry/logging. */
  label?:     string;
  /** If true, fire a recordEvent('retry') on each failed attempt. */
  trace?:     boolean;
  /** Cancel signal — if `signal.aborted` becomes true between attempts,
   *  retries stop and the current error is returned. */
  signal?:    AbortSignal;
}

export interface RetryResult<T> {
  ok:        boolean;
  value?:    T;
  error?:    any;
  attempts:  number;
}

export async function withRetry<T>(op: () => Promise<T>, opts: RetryOpts<T> = {}): Promise<RetryResult<T>> {
  const retries  = Math.max(0, opts.retries ?? 2);
  const baseMs   = opts.baseMs ?? 400;
  const factor   = opts.factor ?? 2;
  const maxMs    = opts.maxMs  ?? 8000;
  const retryOn  = opts.retryOn ?? (() => true);
  const label    = opts.label ?? 'withRetry';

  let lastErr: any = undefined;
  for (let attempt = 0; attempt <= retries; attempt++) {
    if (opts.signal?.aborted) return { ok: false, error: 'aborted', attempts: attempt };
    try {
      const value = await op();
      return { ok: true, value, attempts: attempt + 1 };
    } catch (e) {
      lastErr = e;
      if (!retryOn(e) || attempt >= retries) break;
      if (opts.trace) {
        try { recordEvent(label, 'retry', 'warn', { attempt: attempt + 1, err: String((e as any)?.message || e) }); } catch {}
      }
      const base = Math.min(maxMs, baseMs * Math.pow(factor, attempt));
      // ★ Add ±25% jitter so concurrent retriers don't dog-pile a recovered backend.
      const jitter = base * (Math.random() * 0.5 - 0.25);
      const wait = Math.max(50, Math.floor(base + jitter));
      await new Promise(r => setTimeout(r, wait));
    }
  }
  return { ok: false, error: lastErr, attempts: retries + 1 };
}

/** Promise.all but per-promise error isolation. Always resolves. */
export async function resolveAllSafe<T>(promises: Promise<T>[]): Promise<Array<{ ok: boolean; value?: T; error?: any }>> {
  return Promise.all(promises.map(p =>
    p.then(value => ({ ok: true, value }))
     .catch(error => ({ ok: false, error }))
  ));
}

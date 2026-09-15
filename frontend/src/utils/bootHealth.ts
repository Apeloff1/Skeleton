/**
 * src/utils/bootHealth.ts — boot-time backend health probe with retry budget.
 *
 * The probe bypasses the shared apiClient circuit breaker so a cold backend
 * never poisons normal application requests. Callers can also provide a
 * tighter per-attempt timeout for startup paths where backend availability is
 * useful telemetry, but must not delay the first interactive screen.
 */
const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';

export interface BootHealthResult {
  ok: boolean;
  attempts: number;
  latency_ms: number;
  version?: number;
  lastError?: string | null;
}

const DEFAULT_RETRIES = 6;
const BASE_BACKOFF_MS = 600;
const DEFAULT_ATTEMPT_TIMEOUT_MS = 7_000;

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new Error('aborted'));
      return;
    }

    let settled = false;
    const finish = (fn: () => void) => {
      if (settled) return;
      settled = true;
      signal?.removeEventListener?.('abort', onAbort);
      fn();
    };
    const timer = setTimeout(() => finish(resolve), ms);
    const onAbort = () => {
      clearTimeout(timer);
      finish(() => reject(new Error('aborted')));
    };
    signal?.addEventListener?.('abort', onAbort, { once: true } as any);
  });
}

export async function probeBackend(
  maxAttempts = DEFAULT_RETRIES,
  outerSignal?: AbortSignal,
  perAttemptTimeoutMs = DEFAULT_ATTEMPT_TIMEOUT_MS,
): Promise<BootHealthResult> {
  const t0 = Date.now();
  let attempt = 0;
  let lastError: string | null = null;

  if (!BACKEND) {
    return {
      ok: false,
      attempts: 0,
      latency_ms: Date.now() - t0,
      lastError: 'backend_url_missing',
    };
  }

  const attempts = Math.max(1, Math.floor(maxAttempts));
  const attemptTimeout = Math.max(250, Math.floor(perAttemptTimeoutMs));

  while (attempt < attempts) {
    attempt += 1;
    if (outerSignal?.aborted) {
      lastError = 'aborted';
      break;
    }

    const ac = typeof AbortController !== 'undefined' ? new AbortController() : null;
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      try { ac?.abort(); } catch {}
    }, attemptTimeout);
    const onOuterAbort = () => { try { ac?.abort(); } catch {} };
    outerSignal?.addEventListener?.('abort', onOuterAbort, { once: true } as any);

    try {
      const res = await fetch(`${BACKEND}/api/health`, {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' },
        signal: ac?.signal,
      });
      clearTimeout(timer);
      outerSignal?.removeEventListener?.('abort', onOuterAbort);

      if (res.ok) {
        let version: number | undefined;
        try { version = (await res.json())?.version; } catch { /* body optional */ }
        return {
          ok: true,
          attempts: attempt,
          latency_ms: Date.now() - t0,
          version,
        };
      }
      lastError = `HTTP ${res.status}`;
    } catch (e: any) {
      clearTimeout(timer);
      outerSignal?.removeEventListener?.('abort', onOuterAbort);
      if (outerSignal?.aborted) {
        lastError = 'aborted';
        break;
      }
      lastError = timedOut ? 'timeout' : (e?.message || 'network_error');
    }

    if (attempt < attempts) {
      const wait = Math.min(BASE_BACKOFF_MS * Math.pow(2, attempt - 1), 5_000)
        + Math.floor(Math.random() * 250);
      try {
        await sleep(wait, outerSignal);
      } catch {
        lastError = 'aborted';
        break;
      }
    }
  }

  return {
    ok: false,
    attempts: attempt,
    latency_ms: Date.now() - t0,
    lastError,
  };
}

/**
 * src/utils/bootHealth.ts — boot-time backend health probe with retry budget.
 *
 * Called from BootLauncher / LaunchCascade before serving the first
 * screen. Tries to reach /api/health, tolerating a COLD-START backend
 * (Emergent scales to zero, so the first request after idle can take
 * several seconds while the container wakes).
 *
 * IMPORTANT: this probe uses a RAW fetch and deliberately BYPASSES the
 * shared apiClient circuit breaker. A slow cold-start must NOT count as
 * "consecutive failures" — otherwise the breaker trips OPEN and every
 * later call (and the connectivity banner) fast-fails `circuit_open` for
 * the whole cool-off window, making a healthy backend look permanently
 * unreachable.
 *
 *   { ok: true, version, latency_ms }                        — healthy
 *   { ok: false, attempts, lastError }                        — backend cold
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
const PER_ATTEMPT_TIMEOUT_MS = 7_000;

export async function probeBackend(
  maxAttempts = DEFAULT_RETRIES,
  outerSignal?: AbortSignal,
): Promise<BootHealthResult> {
  const t0 = Date.now();
  let attempt = 0;
  let lastError: string | null = null;

  while (attempt < maxAttempts) {
    attempt += 1;
    if (outerSignal?.aborted) { lastError = 'aborted'; break; }

    // Fresh per-attempt abort timer so a hung request can't outlive its budget.
    const ac = typeof AbortController !== 'undefined' ? new AbortController() : null;
    let timedOut = false;
    const timer = setTimeout(() => { timedOut = true; try { ac?.abort(); } catch {} }, PER_ATTEMPT_TIMEOUT_MS);
    const onOuterAbort = () => { try { ac?.abort(); } catch {} };
    outerSignal?.addEventListener?.('abort', onOuterAbort);

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
        return { ok: true, attempts: attempt, latency_ms: Date.now() - t0, version };
      }
      lastError = `HTTP ${res.status}`;
    } catch (e: any) {
      clearTimeout(timer);
      outerSignal?.removeEventListener?.('abort', onOuterAbort);
      if (outerSignal?.aborted) { lastError = 'aborted'; break; }
      lastError = timedOut ? 'timeout' : (e?.message || 'network_error');
    }

    if (attempt < maxAttempts) {
      const wait = Math.min(BASE_BACKOFF_MS * Math.pow(2, attempt - 1), 5_000) + Math.floor(Math.random() * 250);
      await new Promise(res => setTimeout(res, wait));
    }
  }
  return { ok: false, attempts: attempt, latency_ms: Date.now() - t0, lastError };
}

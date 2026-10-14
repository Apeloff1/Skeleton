/**
 * Truthful, bounded polling for long-running build jobs.
 * Client observation never authorizes cancellation of the backend work.
 */
export type BuildJobPhase = 'pending' | 'completed' | 'failed' | 'cancelled';
export type BuildJobOutcome = {
  phase: Exclude<BuildJobPhase, 'pending'> | 'timeout' | 'aborted';
  checks: number;
  message: string;
};

const SUCCESS = new Set(['done', 'completed', 'complete', 'succeeded', 'success']);
const FAILURE = new Set(['failed', 'failure', 'error']);
const CANCELLED = new Set(['cancelled', 'canceled']);

export function classifyBuildJob(result: unknown): BuildJobPhase {
  if (!result || typeof result !== 'object' || Array.isArray(result)) return 'pending';
  const response = result as Record<string, unknown>;
  const data = response.data && typeof response.data === 'object' && !Array.isArray(response.data)
    ? response.data as Record<string, unknown> : response;
  const raw = data.job_status ?? data.status ?? data.state;
  const state = typeof raw === 'string' ? raw.trim().toLowerCase() : '';
  if (CANCELLED.has(state)) return 'cancelled';
  if (FAILURE.has(state)) return 'failed';
  if (SUCCESS.has(state)) return data.ok === false || data.error ? 'failed' : 'completed';
  return 'pending'; // queued/running/waiting/retrying/unknown are NOT completion.
}

function waitForNext(ms: number, signal?: AbortSignal): Promise<boolean> {
  if (signal?.aborted) return Promise.resolve(false);
  return new Promise(resolve => {
    let settled = false;
    const stop = (continued: boolean) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      signal?.removeEventListener?.('abort', abort);
      resolve(continued);
    };
    const abort = () => stop(false);
    const timer = setTimeout(() => stop(true), ms);
    signal?.addEventListener?.('abort', abort, { once: true });
  });
}

/**
 * Each fetch starts after the prior one has returned; no overlapping poll
 * requests. Results have a finite observation budget and clear failure state.
 */
export async function watchBuildJob(
  fetchStatus: () => Promise<unknown>,
  options: { signal?: AbortSignal; intervalMs?: number; maxChecks?: number; onPending?: (count: number) => void } = {},
): Promise<BuildJobOutcome> {
  const maxChecks = Math.max(1, Math.min(240, Math.floor(options.maxChecks ?? 180)));
  const intervalMs = Math.max(0, Math.min(30_000, options.intervalMs ?? 3_000));
  for (let count = 1; count <= maxChecks; count += 1) {
    if (options.signal?.aborted) return { phase: 'aborted', checks: count - 1, message: 'Monitoring was stopped.' };
    let response: unknown;
    try { response = await fetchStatus(); }
    catch {
      return { phase: 'failed', checks: count, message: 'Lost contact with the build service. Refresh to check its real status.' };
    }
    if (options.signal?.aborted) return { phase: 'aborted', checks: count, message: 'Monitoring was stopped.' };
    if (response && typeof response === 'object' && 'ok' in response &&
        (response as { ok: unknown }).ok === false) {
      return { phase: 'failed', checks: count, message: 'Could not read build job status. Refresh before retrying.' };
    }
    const phase = classifyBuildJob(response);
    if (phase === 'completed') return { phase, checks: count, message: 'Build job completed. Refreshing project state.' };
    if (phase === 'failed') return { phase, checks: count, message: 'Build job reported failure. Inspect the build before retrying.' };
    if (phase === 'cancelled') return { phase, checks: count, message: 'Build job was cancelled.' };
    options.onPending?.(count);
    if (count < maxChecks && !await waitForNext(intervalMs, options.signal)) {
      return { phase: 'aborted', checks: count, message: 'Monitoring was stopped.' };
    }
  }
  return { phase: 'timeout', checks: maxChecks, message: 'Still not confirmed complete. Refresh before starting another stage.' };
}

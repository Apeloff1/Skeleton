/**
 * Long-running build observation is NOT a lease on the backend build.
 *
 * Client monitoring can be aborted, interrupted or disconnected without
 * claiming the build failed or authorizing its cancellation. No arbitrary
 * deadline or step cap is imposed unless the caller explicitly requests one.
 * Adaptive polling keeps multihour observations finite in resource use.
 */
export type BuildJobPhase = 'pending' | 'completed' | 'failed' | 'cancelled';
export type BuildJobOutcome = {
  phase: Exclude<BuildJobPhase, 'pending'> | 'timeout' | 'aborted' | 'disconnected';
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
  if (data.execution !== undefined) {
    if (!data.execution || typeof data.execution !== 'object' || Array.isArray(data.execution)) return 'pending';
    const execution = data.execution as Record<string, unknown>;
    if (['runner_live', 'stop_requested', 'drain_pending', 'partial_artifacts', 'storage_failed'].some(key => typeof execution[key] !== 'boolean')
      || !Number.isSafeInteger(execution.physical_workers) || Number(execution.physical_workers) < 0
      || !Number.isSafeInteger(execution.unflushed_files) || Number(execution.unflushed_files) < 0) return 'pending';
    // A terminal label cannot release observation while physical work remains.
    if (execution.runner_live || Number(execution.physical_workers) > 0 || execution.drain_pending) return 'pending';
    // partial_artifacts reports retained artifact presence, including a
    // successful vault. Stop, write failure and pending flushes block success.
    if (SUCCESS.has(state) && (execution.stop_requested || execution.storage_failed || Number(execution.unflushed_files) > 0)) return 'pending';
  }
  if (CANCELLED.has(state)) return 'cancelled';
  if (FAILURE.has(state)) return 'failed';
  if (SUCCESS.has(state)) return data.ok === false || data.error ? 'failed' : 'completed';
  return 'pending'; // queued, running, retrying or unknown is not success.
}
function bounded(value: number | undefined, fallback: number, min: number, max: number): number {
  return typeof value === 'number' && Number.isFinite(value)
    ? Math.max(min, Math.min(max, Math.floor(value))) : fallback;
}
function waitForNext(ms: number, signal?: AbortSignal): Promise<boolean> {
  if (signal?.aborted) return Promise.resolve(false);
  return new Promise(resolve => {
    let settled = false;
    const onAbort = () => finish(false);
    const finish = (ok: boolean) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      signal?.removeEventListener('abort', onAbort);
      resolve(ok);
    };
    const timer = setTimeout(() => finish(true), ms);
    signal?.addEventListener('abort', onAbort, { once: true });
  });
}
type MonitorOptions = {
  signal?: AbortSignal;
  intervalMs?: number;
  maxIntervalMs?: number;
  maxChecks?: number;
  requestTimeoutMs?: number;
  maxConsecutiveErrors?: number;
  onPending?: (count: number) => void;
};
type ProbeResult = { kind: 'response'; value: unknown } | { kind: 'error' } | { kind: 'aborted' };
async function probeStatus(
  fetchStatus: (signal?: AbortSignal) => Promise<unknown>,
  signal: AbortSignal | undefined,
  timeoutMs: number,
): Promise<ProbeResult> {
  if (signal?.aborted) return { kind: 'aborted' };
  const controller = new AbortController();
  const onAbort = () => controller.abort();
  signal?.addEventListener('abort', onAbort, { once: true });
  if (signal?.aborted) controller.abort();
  let rejectAbort = () => {};
  const aborted = new Promise<never>((_resolve, reject) => {
    rejectAbort = () => reject(new Error('Observation request aborted'));
    if (controller.signal.aborted) rejectAbort();
    else controller.signal.addEventListener('abort', rejectAbort, { once: true });
  });
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const value = await Promise.race([Promise.resolve().then(() => fetchStatus(controller.signal)), aborted]);
    return { kind: 'response', value };
  } catch {
    return { kind: signal?.aborted ? 'aborted' : 'error' };
  } finally {
    clearTimeout(timer);
    controller.signal.removeEventListener('abort', rejectAbort);
    signal?.removeEventListener('abort', onAbort);
  }
}
/**
 * Caller-owned observation. Default unlimited checks means a long AI build
 * is never declared failed for simply taking too long. Each network attempt
 * still has a deadline and the idle poll interval increases to a finite cap.
 */
export async function watchBuildJob(
  fetchStatus: (signal?: AbortSignal) => Promise<unknown>,
  options: MonitorOptions = {},
): Promise<BuildJobOutcome> {
  const checkLimit = options.maxChecks === undefined ? Infinity
    : bounded(options.maxChecks, 180, 1, 100_000);
  const intervalMs = bounded(options.intervalMs, 3_000, 100, 60_000);
  const maxIntervalMs = Math.max(intervalMs, bounded(options.maxIntervalMs, 30_000, 100, 120_000));
  const requestTimeoutMs = bounded(options.requestTimeoutMs, 12_000, 250, 120_000);
  const maxErrors = bounded(options.maxConsecutiveErrors, 5, 1, 100);
  let idle = 0;
  let failedProbes = 0;
  let checks = 0;
  while (checks < checkLimit) {
    if (options.signal?.aborted) return {
      phase: 'aborted', checks, message: 'Monitoring stopped. The backend build was not cancelled.',
    };
    const result = await probeStatus(fetchStatus, options.signal, requestTimeoutMs);
    if (result.kind === 'aborted') return {
      phase: 'aborted', checks, message: 'Monitoring stopped. The backend build was not cancelled.',
    };
    checks++;
    if (result.kind === 'response') {
      // A rejected status read is not evidence that the underlying build
      // failed. Only an explicitly reported terminal job failure is.
      const response = result.value;
      if (!response || typeof response !== 'object' ||
          ('ok' in response && (response as { ok: unknown }).ok === false)) {
        failedProbes++;
      } else {
        failedProbes = 0;
        const phase = classifyBuildJob(response);
        if (phase === 'completed') return { phase, checks, message: 'Build completed.' };
        if (phase === 'failed') return { phase, checks, message: 'Backend reported a failed build.' };
        if (phase === 'cancelled') return { phase, checks, message: 'Backend reported a cancelled build.' };
      }
    } else {
      failedProbes++;
    }
    if (failedProbes >= maxErrors) return {
      phase: 'disconnected', checks,
      message: 'Build status is unavailable. The job may still be running; resume observation later.',
    };
    try { options.onPending?.(checks); } catch { /* UI callback is not authoritative */ }
    if (checks >= checkLimit) break;
    idle = Math.min(idle + 1, 8);
    const delay = Math.min(maxIntervalMs, intervalMs * (2 ** Math.min(5, idle - 1)));
    if (!await waitForNext(delay, options.signal)) return {
      phase: 'aborted', checks, message: 'Monitoring stopped. The backend build was not cancelled.',
    };
  }
  return {
    phase: 'timeout', checks,
    message: 'Observation budget exhausted. The backend build may still be running.',
  };
}

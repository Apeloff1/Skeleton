/**
 * Bridge to the existing authoritative build-status client.
 *
 * One due ledger receipt causes one bounded status fetch. A disconnected
 * monitor is not a failed build. Backend completion is the only terminal
 * evidence. The caller supplies authenticated status retrieval.
 */
import { watchBuildJob } from '../src/product/buildJobLifecycle';
import type { MonthCycleRecord } from './monthCycleLedger';
import type { MonthCycleWorker } from './monthCycleRecovery';

export type BuildCycleStatusFetch = (
  jobId: string, signal?: AbortSignal,
) => Promise<unknown>;

export function buildCycleWorker(fetchStatus: BuildCycleStatusFetch): MonthCycleWorker {
  return async (record: Readonly<MonthCycleRecord>, signal: AbortSignal) => {
    const result = await watchBuildJob(
      nestedSignal => fetchStatus(record.operationId, nestedSignal),
      { signal, maxChecks: 1, maxConsecutiveErrors: 1 },
    );
    if (result.phase === 'completed' || result.phase === 'failed' ||
        result.phase === 'cancelled') return { phase: result.phase };
    if (result.phase === 'timeout') return { phase: 'running' };
    return { phase: 'disconnected' };
  };
}

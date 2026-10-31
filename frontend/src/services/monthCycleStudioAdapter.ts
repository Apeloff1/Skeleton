/**
 * Read-only month-scale studio goal recovery, using the existing governed
 * status endpoint. Never automatically resumes, advances, retries, renews,
 * authorizes, or cancels a production goal.
 */
import { getStudioGoal, type StudioGoal } from '../product/gameStudioAgentClient';
import type { MonthCycleWorker } from './monthCycleRecovery';
import { MonthCycleLedger, type MonthCycleRecord } from './monthCycleLedger';

export function classifyStudioGoalObservation(goal: Pick<
  StudioGoal, 'status' | 'completion' | 'cursor'
>): 'running' | 'completed' | 'failed' | 'cancelled' {
  const state = String(goal.status || '').trim().toLowerCase();
  if (['failed', 'failure'].includes(state)) return 'failed';
  if (['cancelled', 'canceled'].includes(state)) return 'cancelled';
  // A status label without a server-supplied verification receipt is not
  // proof the full original-game pipeline actually completed.
  if (['completed', 'complete', 'succeeded', 'success'].includes(state) &&
      goal.completion?.verified === true) return 'completed';
  return 'running';
}

export function studioGoalCycleWorker(
  fetchGoal: (goalId: string, signal?: AbortSignal) => Promise<
    Pick<StudioGoal, 'status' | 'completion' | 'cursor'>
  > = async (goalId, signal) => getStudioGoal(goalId, { signal }),
): MonthCycleWorker {
  return async (receipt: Readonly<MonthCycleRecord>, signal: AbortSignal) => {
    const goal = await fetchGoal(receipt.operationId, signal);
    const phase = classifyStudioGoalObservation(goal);
    if (typeof goal.cursor !== 'number' || !Number.isSafeInteger(goal.cursor) ||
        goal.cursor < 0) throw new Error('Invalid authoritative studio cursor');
    return { phase, cursor: goal.cursor };
  };
}

export async function registerStudioGoalCycle(
  ledger: MonthCycleLedger, goal: Pick<StudioGoal, 'goal_id' | 'status'>,
  consumerId: string,
): Promise<MonthCycleRecord> {
  if (!goal || !goal.goal_id) throw new Error('Missing canonical goal identity');
  // Repeated registration of the same backend ID is idempotent; terminal
  // receipts never get revived by opening the game studio UI again.
  return ledger.enroll(goal.goal_id, consumerId, 'studio');
}

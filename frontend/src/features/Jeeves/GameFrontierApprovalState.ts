/** GF-P0-58 operator approval state machine for Game Frontier event actions.
 *
 * Pure (no React / RN imports) so it is unit-testable under node:test.
 * An event action may only reach the authorized game runtime after an
 * operator explicitly approves AND confirms it.
 */
export type ApprovalStatus = 'pending' | 'confirming' | 'running' | 'approved' | 'rejected' | 'error';

export type FrontierEventAction = Readonly<{
  id: string;
  label: string;
  editor: string;
  action: string;
  parameters: Record<string, unknown>;
}>;

export type ApprovalEntry = Readonly<{
  action: FrontierEventAction;
  status: ApprovalStatus;
  intent?: 'approve' | 'reject';
  error?: string;
  receipt?: string;
}>;

export type ApprovalEvent =
  | { type: 'request'; action: FrontierEventAction }
  | { type: 'ask'; id: string; intent: 'approve' | 'reject' }
  | { type: 'cancel'; id: string }
  | { type: 'confirm'; id: string }
  | { type: 'succeeded'; id: string; receipt?: string }
  | { type: 'failed'; id: string; error: string }
  | { type: 'retry'; id: string };

export type ApprovalQueue = ReadonlyArray<ApprovalEntry>;

const MAX_QUEUE = 64;

function patch(queue: ApprovalQueue, id: string, allowed: ApprovalStatus[],
               next: (entry: ApprovalEntry) => ApprovalEntry): ApprovalQueue {
  return queue.map(entry => entry.action.id === id && allowed.includes(entry.status) ? next(entry) : entry);
}

export function approvalReducer(queue: ApprovalQueue, event: ApprovalEvent): ApprovalQueue {
  switch (event.type) {
    case 'request':
      if (queue.some(entry => entry.action.id === event.action.id) || queue.length >= MAX_QUEUE) return queue;
      return [...queue, { action: event.action, status: 'pending' }];
    case 'ask':
      return patch(queue, event.id, ['pending'], entry => ({ ...entry, status: 'confirming', intent: event.intent }));
    case 'cancel':
      return patch(queue, event.id, ['confirming'], entry => ({ action: entry.action, status: 'pending' }));
    case 'confirm':
      return patch(queue, event.id, ['confirming'], entry =>
        entry.intent === 'reject'
          ? { action: entry.action, status: 'rejected', intent: 'reject' }
          : { action: entry.action, status: 'running', intent: 'approve' });
    case 'succeeded':
      return patch(queue, event.id, ['running'], entry => ({ ...entry, status: 'approved', receipt: event.receipt }));
    case 'failed':
      return patch(queue, event.id, ['running'], entry => ({ ...entry, status: 'error', error: event.error }));
    case 'retry':
      return patch(queue, event.id, ['error'], entry => ({ action: entry.action, status: 'pending' }));
    default:
      return queue;
  }
}

/** True only for the single transition that is allowed to call the runtime. */
export function mayCallRuntime(before: ApprovalEntry | undefined, after: ApprovalEntry | undefined): boolean {
  return before?.status === 'confirming' && before.intent === 'approve' && after?.status === 'running';
}

export const statusLabel: Record<ApprovalStatus, string> = {
  pending: 'Pending operator approval',
  confirming: 'Awaiting confirmation',
  running: 'Sending to authorized game runtime',
  approved: 'Approved and applied',
  rejected: 'Rejected by operator',
  error: 'Runtime error',
};

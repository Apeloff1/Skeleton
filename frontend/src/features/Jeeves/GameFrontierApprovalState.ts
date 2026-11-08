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
const ACTION_ID = /^[A-Za-z0-9_-]{1,128}$/;
const EDITOR = /^[a-z][a-z0-9-]{0,63}$/;
const OPERATION = /^[a-z][a-z0-9_]{0,127}$/;
const MAX_PARAMETERS_BYTES = 65536;
const MAX_NODES = 2048;

function strictJson(value: unknown, depth = 0, count = { value: 0 },
                    visiting = new Set<object>()): boolean {
  count.value += 1;
  if (count.value > MAX_NODES || depth > 16) return false;
  if (value === null || typeof value === 'string' && value.length <= 16384
      || typeof value === 'boolean') return true;
  if (typeof value === 'number') return Number.isFinite(value);
  if (typeof value !== 'object') return false;
  if (visiting.has(value)) return false;
  if (!Array.isArray(value) && Object.getPrototypeOf(value) !== Object.prototype
      && Object.getPrototypeOf(value) !== null) return false;
  if (Object.keys(value).length > 256) return false;
  visiting.add(value);
  try {
    const keys = Object.keys(value);
    for (const key of keys) {
      const prop = Object.getOwnPropertyDescriptor(value, key);
      if (!prop || !('value' in prop)
          || (Array.isArray(value) ? false : key.length > 128)
          || !strictJson(prop.value, depth + 1, count, visiting)) return false;
    }
    return true;
  } finally {
    visiting.delete(value);
  }
}

function copyApprovedAction(value: FrontierEventAction): FrontierEventAction | null {
  try {
    if (!value || typeof value !== 'object'
        || typeof value.id !== 'string' || !ACTION_ID.test(value.id)
        || typeof value.label !== 'string' || !value.label.trim() || value.label.length > 160
        || typeof value.editor !== 'string' || !EDITOR.test(value.editor)
        || typeof value.action !== 'string' || !OPERATION.test(value.action)
        || !value.parameters || Array.isArray(value.parameters)
        || typeof value.parameters !== 'object' || !strictJson(value.parameters)) return null;
    const encoded = JSON.stringify(value.parameters);
    if (encoded.length > MAX_PARAMETERS_BYTES) return null;
    return Object.freeze({
      id: value.id, label: value.label, editor: value.editor, action: value.action,
      parameters: JSON.parse(encoded) as Record<string, unknown>,
    });
  } catch {
    return null;
  }
}

function patch(queue: ApprovalQueue, id: string, allowed: ApprovalStatus[],
               next: (entry: ApprovalEntry) => ApprovalEntry): ApprovalQueue {
  return queue.map(entry => entry.action.id === id && allowed.includes(entry.status) ? next(entry) : entry);
}

export function approvalReducer(queue: ApprovalQueue, event: ApprovalEvent): ApprovalQueue {
  switch (event.type) {
    case 'request': {
      if (queue.length >= MAX_QUEUE) return queue;
      const action = copyApprovedAction(event.action);
      if (!action || queue.some(entry => entry.action.id === action.id)) return queue;
      return [...queue, { action, status: 'pending' }];
    }
    case 'ask':
      if (event.intent !== 'approve' && event.intent !== 'reject') return queue;
      return patch(queue, event.id, ['pending'], entry => ({ ...entry, status: 'confirming', intent: event.intent }));
    case 'cancel':
      return patch(queue, event.id, ['confirming'], entry => ({ action: entry.action, status: 'pending' }));
    case 'confirm':
      return patch(queue, event.id, ['confirming'], entry => {
        if (entry.intent === 'reject') return { action: entry.action, status: 'rejected', intent: 'reject' };
        if (entry.intent === 'approve') return { action: entry.action, status: 'running', intent: 'approve' };
        return entry;
      });
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
  return !!before && !!after && before.action === after.action
    && before.action.id === after.action.id
    && before.status === 'confirming' && before.intent === 'approve'
    && after.status === 'running' && after.intent === 'approve';
}

export const statusLabel: Record<ApprovalStatus, string> = {
  pending: 'Pending operator approval',
  confirming: 'Awaiting confirmation',
  running: 'Sending to authorized game runtime',
  approved: 'Approved and applied',
  rejected: 'Rejected by operator',
  error: 'Runtime error',
};

/**
 * Read-only P1 product/workspace projection over canonical operation state.
 *
 * OperationClientState owns accepted replay cursor/content mechanics only.
 * OperationSnapshot remains the durable lifecycle authority. This projection
 * derives bounded UI fields from already-accepted stream events and refuses to
 * render an authoritative workspace record until client and server state
 * converge.
 */

import type {
  OperationCanonicalResult,
  OperationClientState,
  OperationSnapshot,
  OperationStreamEvent,
} from './operationStreamReducer';

export const PRODUCT_PROJECTION_SCHEMA_VERSION = 1;

export type WorkspaceBlocker = {
  blockerId: string;
  summary: string;
  evidenceDigest: string | null;
};

export type WorkspaceCost = {
  currency: string;
  spent: number;
  budget: number | null;
};

export type WorkspaceEvidence = {
  source: string;
  digest: string;
  category: string;
};

export type WorkspaceTerminalResult = {
  status: 'completed' | 'failed' | 'cancelled';
  resultRef: string | null;
  messageId: string | null;
  failureCode: string | null;
  finalOutput: string | null;
};

export type WorkspaceProductProjection = {
  schemaVersion: 1;
  operationId: string;
  tenantId: string;
  operationState: string;
  operationVersion: number;
  cursorSequence: number;
  progress: number;
  progressLabel: string;
  blockers: WorkspaceBlocker[];
  cost: WorkspaceCost | null;
  evidence: WorkspaceEvidence[];
  terminalResult: WorkspaceTerminalResult | null;
  writable: false;
};

const TERMINAL_STATES = new Set(['completed', 'failed', 'cancelled']);

const STATE_PROGRESS: Record<string, number> = {
  created: 0.05,
  validated: 0.15,
  authorized: 0.25,
  admitted: 0.35,
  queued: 0.45,
  running: 0.60,
  waiting_for_tool: 0.65,
  waiting_for_user: 0.65,
  retrying: 0.55,
  degraded: 0.50,
  completed: 1,
  failed: 1,
  cancelled: 1,
};

const STATE_BLOCKERS: Record<string, [string, string]> = {
  waiting_for_tool: [
    'state:waiting-for-tool',
    'Waiting for a canonical tool result.',
  ],
  waiting_for_user: [
    'state:waiting-for-user',
    'Waiting for user input.',
  ],
  retrying: [
    'state:retrying',
    'Retry policy is active.',
  ],
  degraded: [
    'state:degraded',
    'Operation is running in degraded mode.',
  ],
};

function record(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function text(value: unknown, field: string, max = 256): string {
  if (typeof value !== 'string' || !value.trim()) {
    throw new Error(`${field} must be non-empty text`);
  }
  const normalized = value.trim();
  if (normalized !== value || normalized.length > max) {
    throw new Error(`${field} must be normalized`);
  }
  return normalized;
}

function sha256(value: unknown, field: string): string {
  const digest = text(value, field, 64);
  if (!/^[0-9a-f]{64}$/.test(digest)) {
    throw new Error(`${field} must be lowercase sha256`);
  }
  return digest;
}

function nonnegative(value: unknown, field: string): number {
  if (
    typeof value !== 'number'
    || !Number.isFinite(value)
    || value < 0
  ) {
    throw new Error(`${field} must be finite and non-negative`);
  }
  return value;
}

function fraction(value: unknown, field: string): number {
  const number = nonnegative(value, field);
  if (number > 1) throw new Error(`${field} must be within [0, 1]`);
  return number;
}

function acceptedEvents(state: OperationClientState): OperationStreamEvent[] {
  const sequences = new Set<number>();
  const eventIds = new Set<string>();
  const rows = [...state.events].sort((a, b) => a.sequence - b.sequence);
  for (const event of rows) {
    if (
      event.operation_id !== state.operationId
      || !Number.isSafeInteger(event.sequence)
      || event.sequence < 1
      || event.sequence > state.lastSequence
    ) {
      throw new Error('workspace projection contains unaccepted event');
    }
    if (sequences.has(event.sequence)) {
      throw new Error('workspace projection contains duplicate sequence');
    }
    if (eventIds.has(event.event_id)) {
      throw new Error('workspace projection contains duplicate event id');
    }
    sequences.add(event.sequence);
    eventIds.add(event.event_id);
  }
  return rows;
}

function projectProgress(
  snapshot: OperationSnapshot,
  events: OperationStreamEvent[],
): [number, string] {
  let progress = STATE_PROGRESS[snapshot.state];
  if (progress === undefined) {
    throw new Error('workspace projection has unsupported operation state');
  }
  let label = snapshot.state.replaceAll('_', ' ');
  for (const event of events) {
    if (!Object.prototype.hasOwnProperty.call(event.payload, 'progress')) {
      continue;
    }
    progress = fraction(event.payload.progress, 'event.progress');
    if (event.payload.progress_label !== undefined) {
      label = text(
        event.payload.progress_label,
        'event.progress_label',
      );
    }
  }
  if (TERMINAL_STATES.has(snapshot.state)) progress = 1;
  return [progress, label];
}

function projectBlockers(
  snapshot: OperationSnapshot,
  events: OperationStreamEvent[],
): WorkspaceBlocker[] {
  const active = new Map<string, WorkspaceBlocker>();
  const derived = STATE_BLOCKERS[snapshot.state];
  if (derived) {
    active.set(derived[0], {
      blockerId: derived[0],
      summary: derived[1],
      evidenceDigest: null,
    });
  }

  for (const event of events) {
    const raw = event.payload.blockers;
    if (raw === undefined) continue;
    if (!Array.isArray(raw)) {
      throw new Error('event.blockers must be a list');
    }
    for (const item of raw) {
      const row = record(item);
      if (!row) throw new Error('blocker entry must be an object');
      const blockerId = text(row.blocker_id, 'blocker_id', 128);
      const enabled = row.active ?? true;
      if (typeof enabled !== 'boolean') {
        throw new Error('blocker active flag must be boolean');
      }
      if (!enabled) {
        active.delete(blockerId);
        continue;
      }
      active.set(blockerId, {
        blockerId,
        summary: text(row.summary, 'blocker summary'),
        evidenceDigest:
          row.evidence_digest === undefined || row.evidence_digest === null
            ? null
            : sha256(row.evidence_digest, 'blocker evidence_digest'),
      });
      if (active.size > 32) throw new Error('blocker limit exceeded');
    }
  }
  return [...active.values()].sort((a, b) =>
    a.blockerId.localeCompare(b.blockerId)
  );
}

function projectCost(events: OperationStreamEvent[]): WorkspaceCost | null {
  let current: WorkspaceCost | null = null;
  for (const event of events) {
    const raw = event.payload.cost;
    if (raw === undefined) continue;
    const row = record(raw);
    if (!row) throw new Error('event.cost must be an object');
    const candidate: WorkspaceCost = {
      currency: text(row.currency, 'cost.currency', 16).toUpperCase(),
      spent: nonnegative(row.spent, 'cost.spent'),
      budget:
        row.budget === undefined || row.budget === null
          ? null
          : nonnegative(row.budget, 'cost.budget'),
    };
    if (
      candidate.budget !== null
      && candidate.spent > candidate.budget
    ) {
      throw new Error('cost spent cannot exceed budget');
    }
    if (current) {
      if (candidate.currency !== current.currency) {
        throw new Error('cost currency cannot change');
      }
      if (candidate.spent < current.spent) {
        throw new Error('cost spent cannot decrease');
      }
      if (
        current.budget !== null
        && candidate.budget !== null
        && candidate.budget !== current.budget
      ) {
        throw new Error('cost budget cannot change');
      }
    }
    current = candidate;
  }
  return current;
}

function projectEvidence(events: OperationStreamEvent[]): WorkspaceEvidence[] {
  const byKey = new Map<string, WorkspaceEvidence>();
  for (const event of events) {
    const raw = event.payload.evidence;
    if (raw === undefined) continue;
    if (!Array.isArray(raw)) {
      throw new Error('event.evidence must be a list');
    }
    for (const item of raw) {
      const row = record(item);
      if (!row) throw new Error('evidence entry must be an object');
      const evidence: WorkspaceEvidence = {
        source: text(row.source, 'evidence.source', 2048),
        digest: sha256(row.digest, 'evidence.digest'),
        category: text(row.category, 'evidence.category', 128),
      };
      const key = `${evidence.source}\u0000${evidence.digest}\u0000${evidence.category}`;
      byKey.set(key, evidence);
      if (byKey.size > 64) throw new Error('evidence limit exceeded');
    }
  }
  return [...byKey.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([, value]) => value);
}

function projectTerminalResult(
  state: OperationClientState,
  snapshot: OperationSnapshot,
  canonicalResult?: OperationCanonicalResult | null,
): WorkspaceTerminalResult | null {
  if (!TERMINAL_STATES.has(snapshot.state)) return null;

  const result = canonicalResult ?? null;
  const status = snapshot.state as 'completed' | 'failed' | 'cancelled';
  if (result && result.status && result.status !== status) {
    throw new Error('canonical terminal result status mismatch');
  }

  if (status === 'completed') {
    if (!state.contentReconciled || state.contentState !== 'canonical') {
      throw new Error('completed workspace result is not canonically reconciled');
    }
    return {
      status,
      resultRef: result?.result_ref ?? state.terminalResultRef,
      messageId: result?.message_id ?? state.terminalMessageId,
      failureCode: result?.failure_code ?? state.failureCode,
      finalOutput:
        result && Object.prototype.hasOwnProperty.call(result, 'final_output')
          ? result.final_output ?? ''
          : state.canonicalAssistantContent ?? '',
    };
  }

  if (state.canonicalAssistantContent !== null) {
    throw new Error('failed/cancelled workspace cannot retain canonical content');
  }
  return {
    status,
    resultRef: result?.result_ref ?? state.terminalResultRef,
    messageId: result?.message_id ?? state.terminalMessageId,
    failureCode: result?.failure_code ?? state.failureCode,
    finalOutput: null,
  };
}

export function projectWorkspaceOperation(
  state: OperationClientState,
  snapshot: OperationSnapshot,
  canonicalResult?: OperationCanonicalResult | null,
): WorkspaceProductProjection {
  if (state.resyncRequired) {
    throw new Error('workspace projection requires authoritative resync');
  }
  if (snapshot.operation_id !== state.operationId) {
    throw new Error('workspace snapshot belongs to a different operation');
  }
  if (!Number.isSafeInteger(snapshot.version) || snapshot.version < 1) {
    throw new Error('workspace snapshot version is invalid');
  }
  if (snapshot.version > state.lastSequence) {
    throw new Error('workspace client cursor is behind durable authority');
  }
  if (state.operationState !== snapshot.state) {
    throw new Error('workspace client state has not converged to durable authority');
  }

  const terminal = TERMINAL_STATES.has(snapshot.state);
  if (state.terminal !== terminal) {
    throw new Error('workspace terminal state has not converged');
  }
  if (state.lastSequence < 1) {
    throw new Error('workspace projection requires accepted stream history');
  }

  const events = acceptedEvents(state);
  const [progress, progressLabel] = projectProgress(snapshot, events);
  return {
    schemaVersion: PRODUCT_PROJECTION_SCHEMA_VERSION,
    operationId: snapshot.operation_id,
    tenantId: snapshot.tenant_id,
    operationState: snapshot.state,
    operationVersion: snapshot.version,
    cursorSequence: state.lastSequence,
    progress,
    progressLabel,
    blockers: projectBlockers(snapshot, events),
    cost: projectCost(events),
    evidence: projectEvidence(events),
    terminalResult: projectTerminalResult(
      state,
      snapshot,
      canonicalResult,
    ),
    writable: false,
  };
}

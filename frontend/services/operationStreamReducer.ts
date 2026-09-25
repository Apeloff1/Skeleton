/** Pure canonical reducer for resumable operation events. */

export const OPERATION_STREAM_SCHEMA_VERSION = 1;
export const MAX_RETAINED_OPERATION_EVENTS = 128;
export const MAX_RETAINED_EVENT_IDS = 256;
export const MAX_OPERATION_CONTENT_CHARS = 262_144;

export const OPERATION_OUTPUT_DELTA_TYPE = 'operation.output.delta';
export const OPERATION_OUTPUT_SNAPSHOT_TYPE = 'operation.output.snapshot';

export interface OperationStreamEvent {
  schema_version: number;
  operation_id: string;
  event_id: string;
  sequence: number;
  type: string;
  timestamp: string;
  payload: Record<string, unknown>;
}

export interface OperationSnapshot {
  operation_id: string;
  tenant_id: string;
  actor_id: string;
  capability: string;
  created_at: string;
  deadline: string;
  idempotency_key: string;
  trace_id: string;
  state: string;
  identity_digest: string;
  version: number;
  updated_at: string;
}

export interface OperationReplayPayload {
  ok: boolean;
  operation: OperationSnapshot;
  events: OperationStreamEvent[];
  after_sequence: number;
  latest_sequence: number;
  terminal: boolean;
}

export type OperationConnectionState =
  | 'idle'
  | 'replaying'
  | 'following'
  | 'terminal'
  | 'resync_required'
  | 'error';

export type OperationContentState =
  | 'empty'
  | 'provisional'
  | 'authoritative'
  | 'discarded';

export interface OperationClientState {
  operationId: string;
  lastSequence: number;
  seenEventIds: string[];
  events: OperationStreamEvent[];
  operationState: string | null;
  terminal: boolean;
  resyncRequired: boolean;
  connection: OperationConnectionState;
  error: string | null;
  provisionalContent: string;
  authoritativeContent: string | null;
  displayContent: string;
  contentState: OperationContentState;
  terminalReconciled: boolean;
}

const TERMINAL_TYPES = new Set([
  'operation.completed',
  'operation.failed',
  'operation.cancelled',
]);

function validSequence(value: unknown): value is number {
  return Number.isInteger(value) && Number(value) > 0;
}

function boundedContent(
  value: string,
  field: string,
): { ok: true; value: string } | { ok: false; error: string } {
  if (value.length > MAX_OPERATION_CONTENT_CHARS) {
    return { ok: false, error: `${field}_exceeds_content_budget` };
  }
  return { ok: true, value };
}

function stringField(
  payload: Record<string, unknown>,
  field: string,
): string | null | undefined {
  if (!(field in payload)) return undefined;
  const value = payload[field];
  if (value === null) return null;
  return typeof value === 'string' ? value : undefined;
}

function terminalFinalOutput(
  payload: Record<string, unknown>,
): { present: boolean; valid: boolean; value: string | null } {
  if ('final_output' in payload) {
    const value = stringField(payload, 'final_output');
    return {
      present: true,
      valid: value !== undefined,
      value: value ?? null,
    };
  }

  if ('result' in payload) {
    const result = payload.result;
    if (!result || typeof result !== 'object' || Array.isArray(result)) {
      return { present: true, valid: false, value: null };
    }
    const object = result as Record<string, unknown>;
    if (!('final_output' in object)) {
      return { present: true, valid: false, value: null };
    }
    const value = stringField(object, 'final_output');
    return {
      present: true,
      valid: value !== undefined,
      value: value ?? null,
    };
  }

  return { present: false, valid: true, value: null };
}

function reduceContent(
  state: OperationClientState,
  event: OperationStreamEvent,
): OperationClientState {
  if (event.type === OPERATION_OUTPUT_DELTA_TYPE) {
    const delta = stringField(event.payload, 'delta');
    if (delta === undefined || delta === null || delta.length === 0) {
      return failOperationResync(state, 'invalid_output_delta');
    }
    const bounded = boundedContent(
      state.provisionalContent + delta,
      'provisional_content',
    );
    if (!bounded.ok) {
      return failOperationResync(state, bounded.error);
    }
    return {
      ...state,
      provisionalContent: bounded.value,
      displayContent: bounded.value,
      contentState: 'provisional',
      terminalReconciled: false,
    };
  }

  if (event.type === OPERATION_OUTPUT_SNAPSHOT_TYPE) {
    const content = stringField(event.payload, 'content');
    if (content === undefined || content === null) {
      return failOperationResync(state, 'invalid_output_snapshot');
    }
    const bounded = boundedContent(content, 'provisional_content');
    if (!bounded.ok) {
      return failOperationResync(state, bounded.error);
    }
    return {
      ...state,
      provisionalContent: bounded.value,
      displayContent: bounded.value,
      contentState: bounded.value ? 'provisional' : 'empty',
      terminalReconciled: false,
    };
  }

  if (!TERMINAL_TYPES.has(event.type)) return state;

  if (event.type !== 'operation.completed') {
    return {
      ...state,
      authoritativeContent: null,
      displayContent: '',
      contentState: state.provisionalContent ? 'discarded' : 'empty',
      terminalReconciled: true,
    };
  }

  const final = terminalFinalOutput(event.payload);
  if (!final.valid) {
    return failOperationResync(state, 'invalid_terminal_result');
  }
  if (!final.present) {
    // Older producers may emit only the authoritative terminal state. Preserve
    // provisional text for continuity, but never relabel it as authoritative.
    return {
      ...state,
      authoritativeContent: null,
      displayContent: state.provisionalContent,
      contentState: state.provisionalContent ? 'provisional' : 'empty',
      terminalReconciled: false,
    };
  }

  const finalText = final.value ?? '';
  const bounded = boundedContent(finalText, 'authoritative_content');
  if (!bounded.ok) {
    return failOperationResync(state, bounded.error);
  }
  return {
    ...state,
    authoritativeContent: bounded.value,
    displayContent: bounded.value,
    contentState: 'authoritative',
    terminalReconciled: true,
  };
}

export function failOperationResync(
  state: OperationClientState,
  error: string,
): OperationClientState {
  return {
    ...state,
    resyncRequired: true,
    connection: 'resync_required',
    error,
  };
}

export function createOperationClientState(
  operationId: string,
  lastSequence = 0,
): OperationClientState {
  const normalized = operationId.trim();
  if (!normalized) throw new Error('operationId is required');
  if (!Number.isInteger(lastSequence) || lastSequence < 0) {
    throw new Error('lastSequence must be a non-negative integer');
  }
  return {
    operationId: normalized,
    lastSequence,
    seenEventIds: [],
    events: [],
    operationState: null,
    terminal: false,
    resyncRequired: false,
    connection: 'idle',
    error: null,
    provisionalContent: '',
    authoritativeContent: null,
    displayContent: '',
    contentState: 'empty',
    terminalReconciled: false,
  };
}

export function reduceOperationEvent(
  state: OperationClientState,
  event: OperationStreamEvent,
): OperationClientState {
  if (state.resyncRequired) return state;
  if (!event || typeof event !== 'object') {
    return failOperationResync(state, 'invalid_event');
  }
  if (event.schema_version !== OPERATION_STREAM_SCHEMA_VERSION) {
    return failOperationResync(state, 'unsupported_schema_version');
  }
  if (event.operation_id !== state.operationId) {
    return failOperationResync(state, 'cross_operation_event');
  }
  if (
    typeof event.event_id !== 'string'
    || !event.event_id.trim()
    || typeof event.type !== 'string'
    || !event.type.trim()
    || !validSequence(event.sequence)
  ) {
    return failOperationResync(state, 'invalid_event_identity');
  }

  const seenIndex = state.seenEventIds.indexOf(event.event_id);
  if (seenIndex >= 0) {
    if (event.sequence <= state.lastSequence) return state;
    return failOperationResync(state, 'duplicate_event_id_conflict');
  }

  if (event.sequence <= state.lastSequence) {
    return failOperationResync(state, 'out_of_order_event');
  }
  if (event.sequence !== state.lastSequence + 1) {
    return failOperationResync(state, 'sequence_gap');
  }
  if (state.terminal) {
    return failOperationResync(state, 'event_after_terminal');
  }

  const contentState = reduceContent(state, event);
  if (contentState.resyncRequired) return contentState;

  const terminal = TERMINAL_TYPES.has(event.type);
  const payloadState = event.payload?.state;
  const seenEventIds = [...state.seenEventIds, event.event_id].slice(
    -MAX_RETAINED_EVENT_IDS,
  );
  const events = [...state.events, event].slice(-MAX_RETAINED_OPERATION_EVENTS);

  return {
    ...contentState,
    lastSequence: event.sequence,
    seenEventIds,
    events,
    operationState:
      typeof payloadState === 'string' ? payloadState : state.operationState,
    terminal,
    resyncRequired: false,
    connection: terminal ? 'terminal' : 'following',
    error: null,
  };
}

export function reduceOperationReplay(
  state: OperationClientState,
  payload: OperationReplayPayload,
): OperationClientState {
  if (!payload || payload.ok !== true || !payload.operation) {
    return { ...state, connection: 'error', error: 'invalid_replay_payload' };
  }
  if (payload.operation.operation_id !== state.operationId) {
    return failOperationResync(state, 'cross_operation_snapshot');
  }
  if (
    !Number.isInteger(payload.after_sequence)
    || payload.after_sequence !== state.lastSequence
  ) {
    return failOperationResync(state, 'cursor_mismatch');
  }

  let next: OperationClientState = {
    ...state,
    connection: 'replaying',
    error: null,
  };
  for (const event of payload.events || []) {
    next = reduceOperationEvent(next, event);
    if (next.resyncRequired) return next;
  }

  const serverTerminal = Boolean(payload.terminal);
  const serverState = payload.operation.state || next.operationState;
  if (
    Number.isInteger(payload.latest_sequence)
    && payload.latest_sequence < next.lastSequence
  ) {
    return failOperationResync(next, 'server_cursor_regressed');
  }
  if (
    Number.isInteger(payload.latest_sequence)
    && payload.latest_sequence > next.lastSequence
    && (payload.events || []).length === 0
  ) {
    return failOperationResync(next, 'server_events_missing');
  }

  return {
    ...next,
    operationState: serverState,
    terminal: next.terminal || serverTerminal,
    connection: next.terminal || serverTerminal ? 'terminal' : 'following',
  };
}

/** Pure canonical reducer for resumable operation events.
 *
 * Streamed assistant content is provisional UI state only. It is never treated
 * as the canonical message/result until a terminal event (or authoritative
 * replay snapshot) supplies committed content. This keeps transport progress
 * separate from durable product truth.
 */

export const OPERATION_STREAM_SCHEMA_VERSION = 1;
export const MAX_RETAINED_OPERATION_EVENTS = 128;
export const MAX_RETAINED_EVENT_IDS = 256;
export const MAX_PROVISIONAL_ASSISTANT_CHARS = 1_000_000;

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

export interface OperationCanonicalResult {
  status: string;
  final_output?: string | null;
  result_ref?: string | null;
  message_id?: string | null;
  failure_code?: string | null;
}

export interface OperationReplayPayload {
  ok: boolean;
  operation: OperationSnapshot;
  events: OperationStreamEvent[];
  after_sequence: number;
  latest_sequence: number;
  stream_latest_sequence?: number;
  has_more?: boolean;
  terminal: boolean;
  canonical_result?: OperationCanonicalResult | null;
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
  | 'canonical'
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

  provisionalAssistantContent: string;
  canonicalAssistantContent: string | null;
  displayedAssistantContent: string;
  contentState: OperationContentState;
  contentReconciled: boolean;
  terminalResultRef: string | null;
  terminalMessageId: string | null;
  failureCode: string | null;
  terminalEventId: string | null;
}

const TERMINAL_TYPES = new Set([
  'operation.completed',
  'operation.failed',
  'operation.cancelled',
  'terminal',
]);

const PROVISIONAL_CONTENT_TYPES = new Set([
  'assistant_content',
  'assistant.content',
  'operation.assistant_content',
]);

function validSequence(value: unknown): value is number {
  return Number.isInteger(value) && Number(value) > 0;
}

function objectValue(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function optionalString(value: unknown): string | null {
  return typeof value === 'string' ? value : null;
}

function terminalState(
  event: OperationStreamEvent,
): 'completed' | 'failed' | 'cancelled' | null {
  if (event.type === 'operation.completed') return 'completed';
  if (event.type === 'operation.failed') return 'failed';
  if (event.type === 'operation.cancelled') return 'cancelled';
  if (event.type !== 'terminal') return null;

  const state = event.payload?.state;
  return state === 'completed' || state === 'failed' || state === 'cancelled'
    ? state
    : null;
}

function canonicalResultFromPayload(
  payload: Record<string, unknown>,
): OperationCanonicalResult | null {
  const nested = objectValue(payload.result);
  const source = nested ?? payload;
  const status = optionalString(source.status)
    ?? optionalString(payload.state)
    ?? '';
  if (!status) return null;

  const finalOutput = source.final_output;
  const resultRef = source.result_ref ?? payload.result_ref;
  const messageId = source.message_id ?? payload.message_id;
  const failureCode = source.failure_code ?? payload.failure_code;

  return {
    status,
    final_output:
      finalOutput === null || typeof finalOutput === 'string'
        ? finalOutput
        : undefined,
    result_ref:
      resultRef === null || typeof resultRef === 'string'
        ? resultRef
        : undefined,
    message_id:
      messageId === null || typeof messageId === 'string'
        ? messageId
        : undefined,
    failure_code:
      failureCode === null || typeof failureCode === 'string'
        ? failureCode
        : undefined,
  };
}

function reconcileTerminalResult(
  state: OperationClientState,
  result: OperationCanonicalResult | null,
  terminalStateValue: 'completed' | 'failed' | 'cancelled',
  terminalEventId: string | null,
): OperationClientState {
  const resultRef = result?.result_ref ?? null;
  const messageId = result?.message_id ?? null;
  const failureCode = result?.failure_code ?? null;

  if (terminalStateValue === 'completed') {
    if (!result || !Object.prototype.hasOwnProperty.call(result, 'final_output')) {
      if (state.provisionalAssistantContent) {
        return failOperationResync(
          {
            ...state,
            terminalEventId,
            terminalResultRef: resultRef,
            terminalMessageId: messageId,
          },
          'completed_without_canonical_content',
        );
      }
      return {
        ...state,
        canonicalAssistantContent: '',
        displayedAssistantContent: '',
        contentState: 'canonical',
        contentReconciled: true,
        terminalResultRef: resultRef,
        terminalMessageId: messageId,
        failureCode,
        terminalEventId,
      };
    }

    const canonical = result.final_output ?? '';
    return {
      ...state,
      canonicalAssistantContent: canonical,
      displayedAssistantContent: canonical,
      contentState: 'canonical',
      contentReconciled: true,
      terminalResultRef: resultRef,
      terminalMessageId: messageId,
      failureCode,
      terminalEventId,
    };
  }

  return {
    ...state,
    provisionalAssistantContent: '',
    canonicalAssistantContent: null,
    displayedAssistantContent: '',
    contentState: 'discarded',
    contentReconciled: true,
    terminalResultRef: resultRef,
    terminalMessageId: messageId,
    failureCode,
    terminalEventId,
  };
}

function reduceProvisionalContent(
  state: OperationClientState,
  event: OperationStreamEvent,
): OperationClientState {
  const text = event.payload?.text;
  if (typeof text !== 'string') {
    return failOperationResync(state, 'invalid_assistant_content');
  }
  const mode = event.payload?.mode ?? 'append';
  if (mode !== 'append' && mode !== 'replace') {
    return failOperationResync(state, 'invalid_assistant_content_mode');
  }
  if (state.contentReconciled) {
    return failOperationResync(state, 'assistant_content_after_reconciliation');
  }

  const provisional = mode === 'replace'
    ? text
    : state.provisionalAssistantContent + text;
  if (provisional.length > MAX_PROVISIONAL_ASSISTANT_CHARS) {
    return failOperationResync(state, 'provisional_content_limit_exceeded');
  }

  return {
    ...state,
    provisionalAssistantContent: provisional,
    displayedAssistantContent: provisional,
    contentState: provisional ? 'provisional' : 'empty',
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

export function operationCursorStorageKey(
  operationId: string,
  consumerId: string,
): string {
  const operation = operationId.trim();
  const consumer = consumerId.trim();
  if (!operation) throw new Error('operationId is required');
  if (!consumer) throw new Error('consumerId is required');
  if (operation.length > 512 || consumer.length > 128) {
    throw new Error('operation cursor identity exceeds maximum length');
  }
  return (
    'codedock:operation-cursor:'
    + encodeURIComponent(consumer)
    + ':'
    + encodeURIComponent(operation)
  );
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
    provisionalAssistantContent: '',
    canonicalAssistantContent: null,
    displayedAssistantContent: '',
    contentState: 'empty',
    contentReconciled: false,
    terminalResultRef: null,
    terminalMessageId: null,
    failureCode: null,
    terminalEventId: null,
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

  const terminalStateValue = terminalState(event);
  if (TERMINAL_TYPES.has(event.type) && terminalStateValue === null) {
    return failOperationResync(state, 'invalid_terminal_state');
  }

  // Project payload effects before committing sequence/event identity. A
  // rejected payload must leave the accepted cursor untouched so replay can
  // start from the last fully reduced event.
  let projected: OperationClientState = state;

  if (PROVISIONAL_CONTENT_TYPES.has(event.type)) {
    projected = reduceProvisionalContent(projected, event);
    if (projected.resyncRequired) return projected;
  }

  if (terminalStateValue !== null) {
    projected = reconcileTerminalResult(
      projected,
      canonicalResultFromPayload(event.payload),
      terminalStateValue,
      event.event_id,
    );
    if (projected.resyncRequired) return projected;
  }

  const payloadState = event.payload?.state;
  const seenEventIds = [...state.seenEventIds, event.event_id].slice(
    -MAX_RETAINED_EVENT_IDS,
  );
  const events = [...state.events, event].slice(-MAX_RETAINED_OPERATION_EVENTS);

  return {
    ...projected,
    lastSequence: event.sequence,
    seenEventIds,
    events,
    operationState:
      terminalStateValue
      ?? (typeof payloadState === 'string' ? payloadState : state.operationState),
    terminal: terminalStateValue !== null,
    resyncRequired: false,
    connection: terminalStateValue !== null ? 'terminal' : 'following',
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
  const streamLatest = payload.stream_latest_sequence;
  const hasMore = payload.has_more;

  if (
    streamLatest !== undefined
    && (
      !Number.isInteger(streamLatest)
      || Number(streamLatest) < next.lastSequence
    )
  ) {
    return failOperationResync(next, 'server_stream_head_invalid');
  }
  if (
    hasMore !== undefined
    && typeof hasMore !== 'boolean'
  ) {
    return failOperationResync(next, 'server_has_more_invalid');
  }
  if (
    typeof streamLatest === 'number'
    && typeof hasMore === 'boolean'
    && hasMore !== (next.lastSequence < streamLatest)
  ) {
    return failOperationResync(next, 'server_has_more_mismatch');
  }
  if (serverTerminal && hasMore === true) {
    return failOperationResync(next, 'terminal_with_unread_events');
  }
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

  if (serverTerminal && !next.terminal) {
    const terminalStateValue = (
      serverState === 'completed'
      || serverState === 'failed'
      || serverState === 'cancelled'
    ) ? serverState : null;
    if (terminalStateValue === null) {
      return failOperationResync(next, 'terminal_snapshot_state_invalid');
    }
    next = reconcileTerminalResult(
      {
        ...next,
        terminal: true,
        operationState: terminalStateValue,
        connection: 'terminal',
      },
      payload.canonical_result ?? null,
      terminalStateValue,
      null,
    );
    if (next.resyncRequired) return next;
  }

  return {
    ...next,
    operationState: serverState,
    terminal: next.terminal || serverTerminal,
    connection: next.terminal || serverTerminal ? 'terminal' : 'following',
  };
}

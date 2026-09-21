/**
 * Canonical client reducer and resumable transport for durable AI operations.
 *
 * The server owns operation truth. This client persists only the last accepted
 * sequence cursor; event payloads remain in memory. Duplicate IDs, sequence
 * gaps, post-terminal events, and cross-operation events fail closed into an
 * explicit resync-required state.
 */

import AsyncStorage from '@react-native-async-storage/async-storage';

import { authHeaders } from '../src/auth/gameforgeAuth';
import api from '../src/utils/apiClient';

export const OPERATION_STREAM_SCHEMA_VERSION = 1;
export const MAX_RETAINED_OPERATION_EVENTS = 128;
export const MAX_RETAINED_EVENT_IDS = 256;

const CURSOR_PREFIX = 'codedock:operation-cursor:';

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
}

export interface FollowOperationOptions {
  signal?: AbortSignal;
  pollMs?: number;
  initialState?: OperationClientState;
  onState?: (state: OperationClientState) => void;
}

const TERMINAL_TYPES = new Set([
  'operation.completed',
  'operation.failed',
  'operation.cancelled',
]);

function validSequence(value: unknown): value is number {
  return Number.isInteger(value) && Number(value) > 0;
}

function failResync(
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

function cursorKey(operationId: string): string {
  return CURSOR_PREFIX + operationId;
}

function delay(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new Error('aborted'));
      return;
    }
    const timer = setTimeout(resolve, ms);
    const onAbort = () => {
      clearTimeout(timer);
      reject(new Error('aborted'));
    };
    signal?.addEventListener('abort', onAbort, { once: true });
    if (signal) {
      setTimeout(() => signal.removeEventListener('abort', onAbort), ms + 1);
    }
  });
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
  };
}

export function reduceOperationEvent(
  state: OperationClientState,
  event: OperationStreamEvent,
): OperationClientState {
  if (state.resyncRequired) return state;
  if (!event || typeof event !== 'object') {
    return failResync(state, 'invalid_event');
  }
  if (event.schema_version !== OPERATION_STREAM_SCHEMA_VERSION) {
    return failResync(state, 'unsupported_schema_version');
  }
  if (event.operation_id !== state.operationId) {
    return failResync(state, 'cross_operation_event');
  }
  if (
    typeof event.event_id !== 'string'
    || !event.event_id.trim()
    || typeof event.type !== 'string'
    || !event.type.trim()
    || !validSequence(event.sequence)
  ) {
    return failResync(state, 'invalid_event_identity');
  }

  const seenIndex = state.seenEventIds.indexOf(event.event_id);
  if (seenIndex >= 0) {
    if (event.sequence <= state.lastSequence) return state;
    return failResync(state, 'duplicate_event_id_conflict');
  }

  if (event.sequence <= state.lastSequence) {
    return failResync(state, 'out_of_order_event');
  }
  if (event.sequence !== state.lastSequence + 1) {
    return failResync(state, 'sequence_gap');
  }
  if (state.terminal) {
    return failResync(state, 'event_after_terminal');
  }

  const terminal = TERMINAL_TYPES.has(event.type);
  const payloadState = event.payload?.state;
  const seenEventIds = [...state.seenEventIds, event.event_id].slice(
    -MAX_RETAINED_EVENT_IDS,
  );
  const events = [...state.events, event].slice(-MAX_RETAINED_OPERATION_EVENTS);

  return {
    ...state,
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
    return failResync(state, 'cross_operation_snapshot');
  }
  if (
    !Number.isInteger(payload.after_sequence)
    || payload.after_sequence !== state.lastSequence
  ) {
    return failResync(state, 'cursor_mismatch');
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
  if (serverTerminal && !next.terminal) {
    // A terminal durable state without its terminal event means this cursor
    // cannot reconstruct the transport history safely.
    if (next.lastSequence < payload.latest_sequence) {
      return failResync(next, 'terminal_event_missing');
    }
  }

  return {
    ...next,
    operationState: serverState,
    terminal: next.terminal || serverTerminal,
    connection: next.terminal || serverTerminal ? 'terminal' : 'following',
  };
}

export async function loadOperationCursor(operationId: string): Promise<number> {
  try {
    const raw = await AsyncStorage.getItem(cursorKey(operationId));
    if (!raw || !/^\d+$/.test(raw)) return 0;
    const value = Number(raw);
    return Number.isSafeInteger(value) && value >= 0 ? value : 0;
  } catch {
    return 0;
  }
}

export async function saveOperationCursor(
  operationId: string,
  sequence: number,
): Promise<void> {
  if (!Number.isSafeInteger(sequence) || sequence < 0) {
    throw new Error('sequence must be a non-negative safe integer');
  }
  await AsyncStorage.setItem(cursorKey(operationId), String(sequence));
}

export async function clearOperationCursor(operationId: string): Promise<void> {
  try {
    await AsyncStorage.removeItem(cursorKey(operationId));
  } catch {}
}

export async function replayOperation(
  state: OperationClientState,
  signal?: AbortSignal,
): Promise<OperationClientState> {
  if (signal?.aborted) return { ...state, connection: 'idle', error: 'aborted' };

  const path =
    `/api/operations/${encodeURIComponent(state.operationId)}/events/replay`
    + `?after_sequence=${state.lastSequence}&limit=250`;
  const result = await api.get<OperationReplayPayload>(path, {
    signal,
    headers: authHeaders(),
    retries: 2,
    timeoutMs: 15_000,
  });

  if (!result.ok || !result.data) {
    if (result.status === 409) {
      return failResync(state, 'replay_gap');
    }
    if (result.error === 'aborted') {
      return { ...state, connection: 'idle', error: 'aborted' };
    }
    return {
      ...state,
      connection: 'error',
      error: result.error || `HTTP ${result.status}`,
    };
  }

  const next = reduceOperationReplay(state, result.data);
  if (!next.resyncRequired && next.lastSequence !== state.lastSequence) {
    try {
      await saveOperationCursor(next.operationId, next.lastSequence);
    } catch {
      return {
        ...next,
        connection: 'error',
        error: 'cursor_persistence_failed',
      };
    }
  }
  return next;
}

export async function resumeOperation(
  operationId: string,
  signal?: AbortSignal,
): Promise<OperationClientState> {
  const cursor = await loadOperationCursor(operationId);
  return replayOperation(createOperationClientState(operationId, cursor), signal);
}

export async function followOperation(
  operationId: string,
  options: FollowOperationOptions = {},
): Promise<OperationClientState> {
  const pollMs = Math.max(100, Math.floor(options.pollMs ?? 750));
  let state = options.initialState
    ?? createOperationClientState(operationId, await loadOperationCursor(operationId));

  options.onState?.(state);

  while (!state.terminal && !state.resyncRequired && !options.signal?.aborted) {
    const before = state.lastSequence;
    state = await replayOperation(state, options.signal);
    options.onState?.(state);

    if (
      state.terminal
      || state.resyncRequired
      || state.connection === 'error'
      || options.signal?.aborted
    ) {
      break;
    }

    if (state.lastSequence === before) {
      try {
        await delay(pollMs, options.signal);
      } catch {
        break;
      }
    }
  }

  return state;
}

export async function cancelOperation(
  operationId: string,
  signal?: AbortSignal,
): Promise<{ ok: boolean; changed?: boolean; operation?: OperationSnapshot; error?: string }> {
  const result = await api.post<any>(
    `/api/operations/${encodeURIComponent(operationId)}/cancel`,
    {},
    {
      signal,
      headers: authHeaders(),
      idempotencyKey: `cancel:${operationId}`,
      retries: 2,
      timeoutMs: 15_000,
    },
  );
  if (!result.ok || !result.data) {
    return { ok: false, error: result.error || `HTTP ${result.status}` };
  }
  return {
    ok: true,
    changed: Boolean(result.data.changed),
    operation: result.data.operation,
  };
}

export async function resyncOperation(
  operationId: string,
  signal?: AbortSignal,
): Promise<OperationClientState> {
  await clearOperationCursor(operationId);
  return replayOperation(createOperationClientState(operationId, 0), signal);
}

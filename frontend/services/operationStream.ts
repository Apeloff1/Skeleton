/**
 * Resumable network/storage client for canonical durable AI operations.
 *
 * The pure reducer lives in operationStreamReducer.ts so ordering semantics are
 * executable under Node CI. This layer owns authenticated replay/cancel calls
 * plus cursor-only persistence. Event payloads are intentionally not persisted.
 */

import AsyncStorage from '@react-native-async-storage/async-storage';

import { authHeaders } from '../src/auth/gameforgeAuth';
import api from '../src/utils/apiClient';
import {
  OperationClientState,
  OperationReplayPayload,
  OperationSnapshot,
  createOperationClientState,
  failOperationResync,
  reduceOperationReplay,
} from './operationStreamReducer';

export * from './operationStreamReducer';

const CURSOR_PREFIX = 'codedock:operation-cursor:';

function newConsumerId(): string {
  try {
    const randomUUID = (globalThis as any)?.crypto?.randomUUID;
    if (typeof randomUUID === 'function') {
      return `client-${randomUUID.call((globalThis as any).crypto)}`;
    }
  } catch {}
  return `client-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 14)}`;
}

/**
 * One consumer lease identity per running app session. It is not a credential
 * and is intentionally not persisted: a restarted client gets a new lease,
 * while the durable replay cursor remains operation-scoped.
 */
export const OPERATION_CONSUMER_ID = newConsumerId();

export interface FollowOperationOptions {
  signal?: AbortSignal;
  pollMs?: number;
  initialState?: OperationClientState;
  onState?: (state: OperationClientState) => void;
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

    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(timer);
      signal?.removeEventListener('abort', onAbort);
      reject(new Error('aborted'));
    };
    signal?.addEventListener('abort', onAbort, { once: true });
  });
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

async function acknowledgeOperationCursor(
  state: OperationClientState,
  signal?: AbortSignal,
): Promise<{ ok: boolean; error?: string }> {
  const result = await api.post<any>(
    `/api/operations/${encodeURIComponent(state.operationId)}/events/ack`,
    {
      consumer_id: OPERATION_CONSUMER_ID,
      sequence: state.lastSequence,
    },
    {
      signal,
      headers: authHeaders(),
      idempotencyKey:
        `operation-ack:${state.operationId}:${OPERATION_CONSUMER_ID}:${state.lastSequence}`,
      retries: 2,
      timeoutMs: 15_000,
    },
  );
  if (!result.ok) {
    return {
      ok: false,
      error: result.error || `HTTP ${result.status}`,
    };
  }
  return { ok: true };
}


export async function replayOperation(
  state: OperationClientState,
  signal?: AbortSignal,
): Promise<OperationClientState> {
  if (signal?.aborted) {
    return { ...state, connection: 'idle', error: 'aborted' };
  }

  const path =
    `/api/operations/${encodeURIComponent(state.operationId)}/events/replay`
    + `?consumer_id=${encodeURIComponent(OPERATION_CONSUMER_ID)}`
    + `&after_sequence=${state.lastSequence}&limit=250`;
  const result = await api.get<OperationReplayPayload>(path, {
    signal,
    headers: authHeaders(),
    retries: 2,
    timeoutMs: 15_000,
  });

  if (!result.ok || !result.data) {
    if (result.status === 409) {
      return failOperationResync(state, 'replay_gap');
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
  if (next.resyncRequired) return next;

  if (next.lastSequence !== state.lastSequence) {
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

  const acknowledgement = await acknowledgeOperationCursor(next, signal);
  if (!acknowledgement.ok) {
    if (signal?.aborted || acknowledgement.error === 'aborted') {
      return { ...next, connection: 'idle', error: 'aborted' };
    }
    return {
      ...next,
      connection: 'error',
      error: `cursor_ack_failed:${acknowledgement.error || 'unknown'}`,
    };
  }
  return next;
}

export async function resumeOperation(
  operationId: string,
  signal?: AbortSignal,
): Promise<OperationClientState> {
  const cursor = await loadOperationCursor(operationId);
  return replayOperation(
    createOperationClientState(operationId, cursor),
    signal,
  );
}

export async function followOperation(
  operationId: string,
  options: FollowOperationOptions = {},
): Promise<OperationClientState> {
  const pollMs = Math.max(100, Math.floor(options.pollMs ?? 750));
  let state = options.initialState
    ?? createOperationClientState(
      operationId,
      await loadOperationCursor(operationId),
    );

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
): Promise<{
  ok: boolean;
  changed?: boolean;
  operation?: OperationSnapshot;
  error?: string;
}> {
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
    return {
      ok: false,
      error: result.error || `HTTP ${result.status}`,
    };
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
  return replayOperation(
    createOperationClientState(operationId, 0),
    signal,
  );
}

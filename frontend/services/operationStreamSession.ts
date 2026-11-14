/**
 * Injectable browser-session runtime for canonical durable operation streams.
 *
 * The runtime owns only session behavior: replay, cursor persistence,
 * authoritative resync, cancellation and bounded follow. Network/auth/storage
 * adapters are injected so the same semantics can be exercised in Node CI,
 * browsers, React Native, and assembled product journeys.
 */

import {
  createOperationClientState,
  failOperationResync,
  reduceOperationReplay,
} from './operationStreamReducer.ts';
import type {
  OperationCanonicalResult,
  OperationClientState,
  OperationReplayPayload,
  OperationSnapshot,
} from './operationStreamReducer.ts';

export interface OperationSessionCursorStore {
  load(operationId: string, consumerId: string): Promise<number>;
  save(operationId: string, consumerId: string, sequence: number): Promise<void>;
  clear(operationId: string, consumerId: string): Promise<void>;
}

export interface OperationSessionResyncSnapshot {
  ok: boolean;
  operation: OperationSnapshot;
  compacted_through: number;
  resume_after_sequence: number;
  latest_sequence: number;
  terminal: boolean;
  active_consumer_count: number;
  canonical_result?: OperationCanonicalResult | null;
}

export interface OperationSessionCancelResult {
  ok: boolean;
  changed?: boolean;
  operation?: OperationSnapshot;
  error?: string;
}

export interface OperationSessionTransport {
  replay(
    operationId: string,
    consumerId: string,
    afterSequence: number,
    limit: number,
    signal?: AbortSignal,
  ): Promise<
    | { ok: true; payload: OperationReplayPayload }
    | { ok: false; replayGap?: boolean; error?: string }
  >;

  acknowledge(
    operationId: string,
    consumerId: string,
    sequence: number,
    signal?: AbortSignal,
  ): Promise<{ ok: boolean; error?: string }>;

  resync(
    operationId: string,
    consumerId: string,
    signal?: AbortSignal,
  ): Promise<OperationSessionResyncSnapshot | null>;

  cancel(
    operationId: string,
    signal?: AbortSignal,
  ): Promise<OperationSessionCancelResult>;
}

export interface OperationBrowserSessionOptions {
  consumerId: string;
  replayLimit?: number;
  pollMs?: number;
  maxResyncAttempts?: number;
  initialState?: OperationClientState;
  onState?: (state: OperationClientState) => void;
}

function normalizedConsumerId(value: string): string {
  const consumer = String(value ?? '').trim();
  if (!consumer) throw new Error('consumerId is required');
  if (consumer.length > 128) {
    throw new Error('consumerId exceeds maximum length');
  }
  if (!/^[A-Za-z0-9._:-]+$/.test(consumer)) {
    throw new Error('consumerId contains unsupported characters');
  }
  return consumer;
}

function boundedInteger(
  value: number | undefined,
  fallback: number,
  minimum: number,
  maximum: number,
): number {
  const candidate = value ?? fallback;
  if (!Number.isFinite(candidate)) return fallback;
  return Math.max(minimum, Math.min(maximum, Math.floor(candidate)));
}

function wait(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new Error('aborted'));
      return;
    }
    const onAbort = () => {
      clearTimeout(timer);
      signal?.removeEventListener('abort', onAbort);
      reject(new Error('aborted'));
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', onAbort);
      resolve();
    }, ms);
    signal?.addEventListener('abort', onAbort, { once: true });
  });
}

function validResyncSnapshot(
  operationId: string,
  snapshot: OperationSessionResyncSnapshot | null,
): snapshot is OperationSessionResyncSnapshot {
  return Boolean(
    snapshot
    && snapshot.ok === true
    && snapshot.operation
    && snapshot.operation.operation_id === operationId
    && Number.isSafeInteger(snapshot.compacted_through)
    && snapshot.compacted_through >= 0
    && Number.isSafeInteger(snapshot.resume_after_sequence)
    && snapshot.resume_after_sequence === snapshot.compacted_through
    && Number.isSafeInteger(snapshot.latest_sequence)
    && snapshot.latest_sequence >= snapshot.compacted_through
    && Number.isSafeInteger(snapshot.active_consumer_count)
    && snapshot.active_consumer_count >= 0,
  );
}

export class OperationBrowserSession {
  readonly operationId: string;
  readonly consumerId: string;
  readonly transport: OperationSessionTransport;
  readonly cursorStore: OperationSessionCursorStore;
  readonly replayLimit: number;
  readonly pollMs: number;
  readonly maxResyncAttempts: number;
  readonly onState?: (state: OperationClientState) => void;

  private current: OperationClientState | null;

  constructor(
    operationId: string,
    transport: OperationSessionTransport,
    cursorStore: OperationSessionCursorStore,
    options: OperationBrowserSessionOptions,
  ) {
    const operation = String(operationId ?? '').trim();
    if (!operation) throw new Error('operationId is required');
    if (!transport) throw new Error('transport is required');
    if (!cursorStore) throw new Error('cursorStore is required');

    this.operationId = operation;
    this.consumerId = normalizedConsumerId(options.consumerId);
    this.transport = transport;
    this.cursorStore = cursorStore;
    this.replayLimit = boundedInteger(options.replayLimit, 64, 1, 512);
    this.pollMs = boundedInteger(options.pollMs, 750, 100, 60_000);
    this.maxResyncAttempts = boundedInteger(
      options.maxResyncAttempts,
      2,
      0,
      5,
    );
    this.onState = options.onState;
    this.current = options.initialState ?? null;

    if (
      this.current !== null
      && this.current.operationId !== this.operationId
    ) {
      throw new Error('initialState belongs to another operation');
    }
  }

  get state(): OperationClientState | null {
    return this.current;
  }

  private publish(state: OperationClientState): OperationClientState {
    this.current = state;
    this.onState?.(state);
    return state;
  }

  private async baseState(): Promise<OperationClientState> {
    if (this.current !== null) return this.current;
    let cursor = 0;
    try {
      cursor = await this.cursorStore.load(
        this.operationId,
        this.consumerId,
      );
    } catch {
      cursor = 0;
    }
    if (!Number.isSafeInteger(cursor) || cursor < 0) cursor = 0;
    return this.publish(
      createOperationClientState(this.operationId, cursor),
    );
  }

  async replayOnce(signal?: AbortSignal): Promise<OperationClientState> {
    let state = await this.baseState();
    if (signal?.aborted) {
      return this.publish({
        ...state,
        connection: 'idle',
        error: 'aborted',
      });
    }

    const response = await this.transport.replay(
      this.operationId,
      this.consumerId,
      state.lastSequence,
      this.replayLimit,
      signal,
    );

    if (!response.ok) {
      if (response.replayGap) {
        return this.publish(
          failOperationResync(state, 'replay_gap'),
        );
      }
      if (signal?.aborted || response.error === 'aborted') {
        return this.publish({
          ...state,
          connection: 'idle',
          error: 'aborted',
        });
      }
      return this.publish({
        ...state,
        connection: 'error',
        error: response.error ?? 'replay_failed',
      });
    }

    const next = reduceOperationReplay(state, response.payload);
    if (next.resyncRequired) return this.publish(next);

    if (next.lastSequence !== state.lastSequence) {
      try {
        await this.cursorStore.save(
          this.operationId,
          this.consumerId,
          next.lastSequence,
        );
      } catch {
        return this.publish({
          ...next,
          connection: 'error',
          error: 'cursor_persistence_failed',
        });
      }
    }

    const ack = await this.transport.acknowledge(
      this.operationId,
      this.consumerId,
      next.lastSequence,
      signal,
    );
    if (!ack.ok) {
      if (signal?.aborted || ack.error === 'aborted') {
        return this.publish({
          ...next,
          connection: 'idle',
          error: 'aborted',
        });
      }
      return this.publish({
        ...next,
        connection: 'error',
        error: 'cursor_ack_failed:' + (ack.error ?? 'unknown'),
      });
    }

    return this.publish(next);
  }

  async resync(
    signal?: AbortSignal,
    maxAttempts = this.maxResyncAttempts,
  ): Promise<OperationClientState> {
    const attempts = boundedInteger(maxAttempts, 1, 1, 5);
    let last = failOperationResync(
      createOperationClientState(this.operationId),
      'replay_gap',
    );

    for (let attempt = 0; attempt < attempts; attempt += 1) {
      if (signal?.aborted) {
        return this.publish({
          ...last,
          connection: 'idle',
          error: 'aborted',
        });
      }

      const snapshot = await this.transport.resync(
        this.operationId,
        this.consumerId,
        signal,
      );
      if (!validResyncSnapshot(this.operationId, snapshot)) {
        return this.publish({
          ...last,
          connection: 'error',
          error: 'authoritative_resync_unavailable',
        });
      }

      const floor = snapshot.resume_after_sequence;
      try {
        await this.cursorStore.save(
          this.operationId,
          this.consumerId,
          floor,
        );
      } catch {
        return this.publish({
          ...last,
          connection: 'error',
          error: 'cursor_persistence_failed',
        });
      }

      this.current = {
        ...createOperationClientState(this.operationId, floor),
        operationState: snapshot.operation.state,
        // Keep the local reducer non-terminal until it has reconciled the
        // authoritative canonical result or terminal event.
        terminal: false,
        connection: 'replaying',
        resyncRequired: false,
        error: null,
      };

      if (snapshot.terminal && snapshot.latest_sequence === floor) {
        const terminal = reduceOperationReplay(this.current, {
          ok: true,
          operation: snapshot.operation,
          events: [],
          after_sequence: floor,
          latest_sequence: floor,
          stream_latest_sequence: floor,
          has_more: false,
          terminal: true,
          canonical_result: snapshot.canonical_result ?? null,
        });
        return this.publish(terminal);
      }

      const replayed = await this.replayOnce(signal);
      if (!replayed.resyncRequired) return replayed;
      last = replayed;
    }

    return this.publish(last);
  }

  async resume(signal?: AbortSignal): Promise<OperationClientState> {
    const replayed = await this.replayOnce(signal);
    if (!replayed.resyncRequired) return replayed;
    return this.resync(signal);
  }

  async follow(signal?: AbortSignal): Promise<OperationClientState> {
    let state = await this.baseState();
    let resyncAttempts = 0;
    this.publish(state);

    while (!state.terminal && !signal?.aborted) {
      const before = state.lastSequence;
      state = await this.replayOnce(signal);

      if (state.resyncRequired) {
        if (resyncAttempts >= this.maxResyncAttempts) break;
        resyncAttempts += 1;
        state = await this.resync(signal, 1);
        if (
          state.resyncRequired
          || state.connection === 'error'
          || state.terminal
          || signal?.aborted
        ) {
          break;
        }
        continue;
      }

      if (
        state.terminal
        || state.connection === 'error'
        || signal?.aborted
      ) {
        break;
      }

      if (state.lastSequence === before) {
        try {
          await wait(this.pollMs, signal);
        } catch {
          break;
        }
      }
    }

    return this.publish(state);
  }

  async cancel(signal?: AbortSignal): Promise<OperationSessionCancelResult> {
    return this.transport.cancel(this.operationId, signal);
  }

  async clearCursor(): Promise<void> {
    await this.cursorStore.clear(this.operationId, this.consumerId);
    this.current = createOperationClientState(this.operationId);
    this.publish(this.current);
  }
}

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
import type { MonthCycleLedger } from './monthCycleLedger';
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
  maxPollMs?: number;
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
  readonly maxPollMs: number;
  readonly maxResyncAttempts: number;
  readonly onState?: (state: OperationClientState) => void;

  private current: OperationClientState | null;
  private epoch = 0;
  private pendingReplay: Promise<OperationClientState> | null = null;
  // Physical cursor mutations are ordered even when a storage driver finishes
  // after a caller has been aborted or its state generation was invalidated.
  private cursorTail: Promise<void> = Promise.resolve();

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
    this.maxPollMs = Math.max(
      this.pollMs, boundedInteger(options.maxPollMs, 10_000, 100, 60_000),
    );
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
    // Observers are optional UI projections, never operation authorities.
    try { this.onState?.(state); } catch { /* isolate consumer */ }
    return state;
  }

  private enqueueCursorWrite<T>(action: () => Promise<T>): Promise<T> {
    const job = this.cursorTail.then(action);
    this.cursorTail = job.then(() => undefined, () => undefined);
    return job;
  }

  private async baseState(): Promise<OperationClientState> {
    if (this.current !== null) return this.current;
    const generation = this.epoch;
    let cursor = 0;
    try {
      cursor = await this.cursorStore.load(
        this.operationId,
        this.consumerId,
      );
    } catch {
      cursor = 0;
    }
    // An in-flight load must not replace a new state published by clearCursor.
    if (generation !== this.epoch || this.current !== null) {
      return this.current ?? createOperationClientState(this.operationId);
    }
    if (!Number.isSafeInteger(cursor) || cursor < 0) cursor = 0;
    return this.publish(
      createOperationClientState(this.operationId, cursor),
    );
  }

  replayOnce(signal?: AbortSignal): Promise<OperationClientState> {
    if (this.pendingReplay) return this.pendingReplay;
    const generation = this.epoch;
    const work = this.performReplayOnce(signal, generation);
    this.pendingReplay = work;
    const release = () => {
      if (this.pendingReplay === work) this.pendingReplay = null;
    };
    void work.then(release, release);
    return work;
  }

  private async performReplayOnce(signal: AbortSignal | undefined, generation: number): Promise<OperationClientState> {
    let state = await this.baseState();
    if (generation !== this.epoch) return this.current ?? state;
    if (signal?.aborted) {
      return this.publish({
        ...state,
        connection: 'idle',
        error: 'aborted',
      });
    }

    let response: Awaited<ReturnType<OperationSessionTransport['replay']>>;
    try {
      response = await this.transport.replay(
        this.operationId, this.consumerId, state.lastSequence,
        this.replayLimit, signal,
      );
    } catch {
      if (generation !== this.epoch) return this.current ?? state;
      return this.publish({
        ...state, connection: signal?.aborted ? 'idle' : 'error',
        error: signal?.aborted ? 'aborted' : 'replay_transport_unavailable',
      });
    }
    if (generation !== this.epoch) return this.current ?? state;

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
        if (generation !== this.epoch || signal?.aborted) return this.current ?? state;
        await this.enqueueCursorWrite(async () => {
          if (generation !== this.epoch) return;
          await this.cursorStore.save(
            this.operationId, this.consumerId, next.lastSequence,
          );
        });
        if (generation !== this.epoch) return this.current ?? state;
      } catch {
        return this.publish({
          ...next,
          connection: 'error',
          error: 'cursor_persistence_failed',
        });
      }
    }

    let ack: Awaited<ReturnType<OperationSessionTransport['acknowledge']>>;
    try {
      ack = await this.transport.acknowledge(
        this.operationId, this.consumerId, next.lastSequence, signal,
      );
    } catch {
      if (generation !== this.epoch) return this.current ?? state;
      return this.publish({
        ...next, connection: signal?.aborted ? 'idle' : 'error',
        error: signal?.aborted ? 'aborted' : 'cursor_ack_unavailable',
      });
    }
    if (generation !== this.epoch) return this.current ?? state;
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
    const generation = this.epoch;
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

      let snapshot: OperationSessionResyncSnapshot | null = null;
      try {
        snapshot = await this.transport.resync(
          this.operationId, this.consumerId, signal,
        );
      } catch {
        return this.publish({
          ...last, connection: signal?.aborted ? 'idle' : 'error',
          error: signal?.aborted ? 'aborted' : 'authoritative_resync_unavailable',
        });
      }
      if (generation !== this.epoch) {
        return this.current ?? createOperationClientState(this.operationId);
      }
      if (!validResyncSnapshot(this.operationId, snapshot)) {
        return this.publish({
          ...last,
          connection: 'error',
          error: 'authoritative_resync_unavailable',
        });
      }

      const floor = snapshot.resume_after_sequence;
      try {
        await this.enqueueCursorWrite(async () => {
          if (generation !== this.epoch) return;
          await this.cursorStore.save(this.operationId, this.consumerId, floor);
        });
        if (generation !== this.epoch) {
          return this.current ?? createOperationClientState(this.operationId);
        }
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

  /**
   * Persist the operation identity BEFORE touching the network. If the app
   * closes at any point, a later foreground recovery pass can enumerate this
   * receipt and use the canonical replay API to verify its actual state.
   * The cursor store remains authoritative for exact replay checkpoints.
   */
  async resumeDurable(
    ledger: MonthCycleLedger, signal?: AbortSignal,
  ): Promise<OperationClientState> {
    const receipt = await ledger.enroll(this.operationId, this.consumerId, 'operation');
    if (receipt.status === 'terminal_observed' || receipt.status === 'dismissed') {
      // Terminal/dismissed operation is not secretly restarted by the client.
      return this.current ?? this.baseState();
    }
    const observed = await this.resume(signal);
    const now = Date.now();
    const terminalState = observed.terminal && observed.contentReconciled &&
      (observed.operationState === 'completed' ||
        observed.operationState === 'failed' ||
        observed.operationState === 'cancelled')
      ? observed.operationState : null;
    await ledger.observe(receipt, terminalState ? {
      phase: 'terminal_observed', terminalState,
      cursor: observed.lastSequence, now,
    } : {
      phase: observed.connection === 'error' || observed.resyncRequired ||
        observed.connection === 'idle' ? 'disconnected' : 'observing',
      cursor: observed.lastSequence, now, nextCheckAt: now + 5 * 60_000,
    });
    return observed;
  }

  async follow(signal?: AbortSignal): Promise<OperationClientState> {
    let state = await this.baseState();
    let resyncAttempts = 0;
    let idleRounds = 0;
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
        // An idle multi-hour operation should not issue the same status
        // request every 750ms for its entire lifetime. New events immediately
        // reset the backoff so progress remains responsive.
        idleRounds = Math.min(10, idleRounds + 1);
        const delay = Math.min(this.maxPollMs, this.pollMs * (2 ** Math.min(6, idleRounds - 1)));
        try {
          await wait(delay, signal);
        } catch { break; }
      } else {
        idleRounds = 0;
      }
    }

    return this.publish(state);
  }

  async cancel(signal?: AbortSignal): Promise<OperationSessionCancelResult> {
    try { return await this.transport.cancel(this.operationId, signal); }
    catch { return { ok: false, error: signal?.aborted ? 'aborted' : 'cancel_transport_unavailable' }; }
  }

  async clearCursor(): Promise<void> {
    this.epoch++;
    this.pendingReplay = null;
    // Invalidate all in-flight network observations before clearing storage,
    // and commit the clear AFTER any already-started native cursor write.
    this.current = createOperationClientState(this.operationId);
    await this.enqueueCursorWrite(() => this.cursorStore.clear(
      this.operationId, this.consumerId,
    ));
    this.publish(this.current);
  }
}

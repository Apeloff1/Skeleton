import {
  OperationClientState,
  OperationReplayPayload,
  OperationSnapshot,
  createOperationClientState,
  failOperationResync,
  reduceOperationReplay,
} from './operationStreamReducer';

export interface OperationCursorStore {
  get(key: string): Promise<string | null> | string | null;
  set(key: string, value: string): Promise<void> | void;
  remove(key: string): Promise<void> | void;
}

export interface OperationSnapshotPayload {
  ok: boolean;
  operation: OperationSnapshot;
  compacted_through: number;
  latest_sequence: number;
  terminal: boolean;
}

export type FetchLike = (
  input: string,
  init?: RequestInit,
) => Promise<{
  ok: boolean;
  status: number;
  json(): Promise<unknown>;
}>;

export class MemoryOperationCursorStore implements OperationCursorStore {
  private readonly values = new Map<string, string>();

  get(key: string): string | null {
    return this.values.get(key) ?? null;
  }

  set(key: string, value: string): void {
    this.values.set(key, value);
  }

  remove(key: string): void {
    this.values.delete(key);
  }
}

function nonNegativeInteger(value: unknown): number | null {
  return Number.isInteger(value) && Number(value) >= 0 ? Number(value) : null;
}

function consumerId(value: string): string {
  const normalized = value.trim();
  if (!/^[A-Za-z0-9._:-]{1,128}$/.test(normalized)) {
    throw new Error('consumerId is invalid');
  }
  return normalized;
}

export class OperationStreamClient {
  readonly operationId: string;
  readonly consumerId: string;
  readonly baseUrl: string;

  private readonly cursorStore: OperationCursorStore;
  private readonly fetchImpl: FetchLike;
  private stateValue: OperationClientState;

  constructor(options: {
    operationId: string;
    consumerId: string;
    baseUrl?: string;
    cursorStore?: OperationCursorStore;
    fetchImpl?: FetchLike;
  }) {
    const operationId = options.operationId.trim();
    if (!operationId) throw new Error('operationId is required');
    this.operationId = operationId;
    this.consumerId = consumerId(options.consumerId);
    this.baseUrl = (options.baseUrl ?? '').replace(/\/$/, '');
    this.cursorStore = options.cursorStore ?? new MemoryOperationCursorStore();
    this.fetchImpl = options.fetchImpl ?? (fetch as unknown as FetchLike);
    this.stateValue = createOperationClientState(operationId);
  }

  get state(): OperationClientState {
    return this.stateValue;
  }

  private get cursorKey(): string {
    return `operation-stream:${this.consumerId}:${this.operationId}`;
  }

  private endpoint(path: string): string {
    return (
      this.baseUrl
      + '/operations/'
      + encodeURIComponent(this.operationId)
      + path
    );
  }

  async hydrate(): Promise<OperationClientState> {
    const raw = await this.cursorStore.get(this.cursorKey);
    if (raw === null) {
      this.stateValue = createOperationClientState(this.operationId);
      return this.stateValue;
    }
    const parsed = nonNegativeInteger(Number(raw));
    if (parsed === null) {
      await this.cursorStore.remove(this.cursorKey);
      this.stateValue = failOperationResync(
        createOperationClientState(this.operationId),
        'persisted_cursor_invalid',
      );
      return this.stateValue;
    }
    this.stateValue = createOperationClientState(this.operationId, parsed);
    return this.stateValue;
  }

  private async persistCursor(sequence: number): Promise<void> {
    await this.cursorStore.set(this.cursorKey, String(sequence));
  }

  private async acknowledge(sequence: number): Promise<void> {
    const response = await this.fetchImpl(
      this.endpoint('/events/ack'),
      {
        method: 'POST',
        headers: {'content-type': 'application/json'},
        body: JSON.stringify({
          consumer_id: this.consumerId,
          sequence,
        }),
      },
    );
    if (!response.ok) {
      throw new Error('operation_stream_ack_failed');
    }
  }

  async replay(limit = 250): Promise<OperationClientState> {
    if (!Number.isInteger(limit) || limit < 1 || limit > 1000) {
      throw new Error('limit must be within [1, 1000]');
    }
    const query = new URLSearchParams({
      consumer_id: this.consumerId,
      after_sequence: String(this.stateValue.lastSequence),
      limit: String(limit),
    });
    const response = await this.fetchImpl(
      this.endpoint('/events/replay') + '?' + query.toString(),
      {method: 'GET'},
    );

    if (response.status === 409) {
      this.stateValue = failOperationResync(
        this.stateValue,
        'replay_gap',
      );
      return this.resync();
    }
    if (!response.ok) {
      this.stateValue = {
        ...this.stateValue,
        connection: 'error',
        error: 'operation_stream_replay_failed',
      };
      return this.stateValue;
    }

    const payload = await response.json() as OperationReplayPayload;
    const next = reduceOperationReplay(this.stateValue, payload);
    this.stateValue = next;
    if (next.resyncRequired) {
      return this.resync();
    }

    await this.persistCursor(next.lastSequence);
    if (next.lastSequence > 0) {
      await this.acknowledge(next.lastSequence);
    }
    return next;
  }

  async resync(): Promise<OperationClientState> {
    const query = new URLSearchParams({consumer_id: this.consumerId});
    const response = await this.fetchImpl(
      this.endpoint('/events/snapshot') + '?' + query.toString(),
      {method: 'GET'},
    );
    if (!response.ok) {
      this.stateValue = {
        ...this.stateValue,
        resyncRequired: true,
        connection: 'error',
        error: 'operation_stream_resync_failed',
      };
      return this.stateValue;
    }

    const payload = await response.json() as OperationSnapshotPayload;
    if (
      payload.ok !== true
      || !payload.operation
      || payload.operation.operation_id !== this.operationId
    ) {
      this.stateValue = failOperationResync(
        this.stateValue,
        'invalid_resync_snapshot',
      );
      return this.stateValue;
    }
    const latest = nonNegativeInteger(payload.latest_sequence);
    const compacted = nonNegativeInteger(payload.compacted_through);
    if (latest === null || compacted === null || compacted > latest) {
      this.stateValue = failOperationResync(
        this.stateValue,
        'invalid_resync_cursor',
      );
      return this.stateValue;
    }

    this.stateValue = {
      ...createOperationClientState(this.operationId, latest),
      operationState: payload.operation.state,
      terminal: Boolean(payload.terminal),
      connection: payload.terminal ? 'terminal' : 'following',
      resyncRequired: false,
      error: null,
    };
    await this.persistCursor(latest);
    if (latest > 0) {
      await this.acknowledge(latest);
    }
    return this.stateValue;
  }

  async reset(): Promise<OperationClientState> {
    await this.cursorStore.remove(this.cursorKey);
    this.stateValue = createOperationClientState(this.operationId);
    return this.stateValue;
  }
}

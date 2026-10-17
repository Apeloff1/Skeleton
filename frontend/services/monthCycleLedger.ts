/**
 * Crash-recoverable CLIENT OBSERVATION receipts for week/month studio work.
 *
 * The backend remains the sole authority for completion, cancellation,
 * checkpoints and any work being performed. These receipts only tell a
 * restarted client what to inspect and where its verified cursor last stood.
 *
 * Alternating checksummed slots protect against torn/garbled JSON and avoid
 * replacing the last known-good receipt during a staged write. Native writes
 * are serialized per storage identity. This is NOT a cross-process lock or
 * an exactly-once server transaction.
 */
export type MonthCycleKind = 'studio' | 'build' | 'training' | 'operation';
export type MonthCycleStatus = 'observing' | 'disconnected' | 'terminal_observed' | 'dismissed';
export interface MonthCycleRecord {
  operationId: string;
  consumerId: string;
  kind: MonthCycleKind;
  incarnation: string;
  status: MonthCycleStatus;
  cursor: number;
  firstSeenAt: number;
  lastSeenAt: number;
  nextCheckAt: number;
  failures: number;
  terminalState: 'completed' | 'failed' | 'cancelled' | null;
}
export interface MonthCycleStorage {
  getItem(key: string): Promise<string | null>;
  setItem(key: string, value: string): Promise<void>;
}
interface LedgerPayload { version: 1; revision: number; records: MonthCycleRecord[] }
interface LedgerSlot extends LedgerPayload { checksum: string }
const MAX_RECORDS = 128;
const MAX_CHARS = 128 * 1024;
const RETAIN_TERMINAL_MS = 180 * 24 * 60 * 60 * 1000;
const MAX_CLOCK = 8_640_000_000_000_000;
const storageLocks = new WeakMap<object, Map<string, Promise<void>>>();

const identity = (value: string, max: number) =>
  typeof value === 'string' && value.length > 0 && value.length <= max &&
  /^[A-Za-z0-9._:-]+$/.test(value);
const clockValue = (value: unknown): value is number =>
  typeof value === 'number' && Number.isSafeInteger(value) &&
  value >= 0 && value <= MAX_CLOCK;
function fingerprint(value: string): string {
  // Integrity only; not an authentication signature or cryptographic hash.
  let hash = 2166136261;
  for (let i = 0; i < value.length; i++) {
    hash ^= value.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16).padStart(8, '0');
}
function validRecord(r: unknown): r is MonthCycleRecord {
  if (!r || typeof r !== 'object') return false;
  const x = r as MonthCycleRecord;
  return identity(x.operationId, 128) && identity(x.consumerId, 128) &&
    ['studio', 'build', 'training', 'operation'].includes(x.kind) &&
    identity(x.incarnation, 96) &&
    ['observing', 'disconnected', 'terminal_observed', 'dismissed'].includes(x.status) &&
    clockValue(x.cursor) && clockValue(x.firstSeenAt) &&
    clockValue(x.lastSeenAt) && clockValue(x.nextCheckAt) &&
    clockValue(x.failures) && x.failures <= 1000 &&
    (x.terminalState === null || ['completed', 'failed', 'cancelled'].includes(x.terminalState));
}
function decode(raw: string | null): LedgerPayload | null {
  if (!raw || raw.length > MAX_CHARS) return null;
  try {
    const slot = JSON.parse(raw) as LedgerSlot;
    if (!slot || slot.version !== 1 || !clockValue(slot.revision) ||
        !Array.isArray(slot.records) || slot.records.length > MAX_RECORDS) return null;
    const payload: LedgerPayload = {
      version: 1, revision: slot.revision, records: slot.records,
    };
    if (!slot.records.every(validRecord)) return null;
    const ids = new Set(slot.records.map(x => x.operationId + ':' + x.consumerId));
    if (ids.size !== slot.records.length) return null;
    if (fingerprint(JSON.stringify(payload)) !== slot.checksum) return null;
    return payload;
  } catch { return null; }
}
function serialize(payload: LedgerPayload): string {
  const data = JSON.stringify({ ...payload, checksum: fingerprint(JSON.stringify(payload)) });
  if (data.length > MAX_CHARS) throw new Error('Month-cycle ledger storage budget exceeded');
  return data;
}
function clone(record: MonthCycleRecord): MonthCycleRecord { return { ...record }; }
function time(now: number): number {
  if (!clockValue(now)) throw new Error('Invalid observation clock');
  return now;
}
export class MonthCycleLedger {
  private readonly firstKey: string;
  private readonly secondKey: string;
  constructor(private readonly storage: MonthCycleStorage, namespace: string) {
    if (!storage || typeof storage.getItem !== 'function' ||
        typeof storage.setItem !== 'function') throw new Error('Storage adapter required');
    if (!identity(namespace, 96)) throw new Error('Invalid ledger namespace');
    this.firstKey = '@codedock:month-cycle:v1:' + namespace + ':a';
    this.secondKey = '@codedock:month-cycle:v1:' + namespace + ':b';
  }
  private async read(): Promise<LedgerPayload> {
    const [rawA, rawB] = await Promise.all([
      this.storage.getItem(this.firstKey), this.storage.getItem(this.secondKey),
    ]);
    const a = decode(rawA), b = decode(rawB);
    if (!a && !b && (rawA !== null || rawB !== null)) {
      throw new Error('Month-cycle receipts corrupt: refusing to discard active work');
    }
    if (!a && !b) return { version: 1, revision: 0, records: [] };
    if (!a) return b!;
    if (!b) return a;
    return b.revision > a.revision ? b : a;
  }
  private async update<T>(fn: (current: LedgerPayload) => T): Promise<T> {
    const locks = storageLocks.get(this.storage) ?? new Map<string, Promise<void>>();
    storageLocks.set(this.storage, locks);
    const key = this.firstKey;
    const prior = locks.get(key) ?? Promise.resolve();
    let release!: () => void;
    const tail = new Promise<void>(resolve => { release = resolve; });
    locks.set(key, tail);
    await prior;
    try {
      const payload = await this.read();
      const before = JSON.stringify(payload.records);
      const result = fn(payload);
      if (JSON.stringify(payload.records) !== before) {
        const next = { ...payload, revision: payload.revision + 1 };
        if (!clockValue(next.revision)) throw new Error('Ledger revision overflow');
        const writeKey = next.revision % 2 === 1 ? this.firstKey : this.secondKey;
        await this.storage.setItem(writeKey, serialize(next));
      }
      return result;
    } finally {
      release();
      if (locks.get(key) === tail) locks.delete(key);
      if (locks.size === 0) storageLocks.delete(this.storage);
    }
  }
  async inspect(): Promise<MonthCycleRecord[]> {
    return (await this.read()).records.map(clone);
  }
  async enroll(
    operationId: string, consumerId: string, kind: MonthCycleKind,
    now = Date.now(),
  ): Promise<MonthCycleRecord> {
    if (!identity(operationId, 128) || !identity(consumerId, 128) ||
        !['studio', 'build', 'training', 'operation'].includes(kind)) {
      throw new Error('Invalid work-cycle identity');
    }
    const at = time(now);
    return this.update(payload => {
      const existing = payload.records.find(
        r => r.operationId === operationId && r.consumerId === consumerId,
      );
      if (existing && existing.status !== 'dismissed' && existing.status !== 'terminal_observed') {
        if (existing.kind !== kind) throw new Error('Work-cycle kind mismatch');
        return clone(existing);
      }
      if (payload.records.length >= MAX_RECORDS) {
        // Never evict an active job to admit another one.
        throw new Error('Month-cycle registry saturated; archive completed receipts explicitly');
      }
      const record: MonthCycleRecord = {
        operationId, consumerId, kind,
        incarnation: (payload.revision + 1).toString(36) + ':' + at.toString(36),
        status: 'observing', cursor: 0, firstSeenAt: at, lastSeenAt: at,
        nextCheckAt: at, failures: 0, terminalState: null,
      };
      payload.records.push(record);
      return clone(record);
    });
  }
  async observe(
    token: Pick<MonthCycleRecord, 'operationId' | 'consumerId' | 'incarnation'>,
    input: { cursor?: number; phase: 'observing' | 'disconnected' | 'terminal_observed';
      terminalState?: 'completed' | 'failed' | 'cancelled'; nextCheckAt?: number; now?: number },
  ): Promise<MonthCycleRecord | null> {
    const now = time(input.now ?? Date.now());
    const due = time(input.nextCheckAt ?? now);
    if (due < now || due - now > 7 * 24 * 60 * 60 * 1000) {
      throw new Error('Next observation outside bounded horizon');
    }
    if (input.cursor !== undefined && !clockValue(input.cursor)) {
      throw new Error('Invalid cursor');
    }
    if (input.phase === 'terminal_observed' &&
        !['completed', 'failed', 'cancelled'].includes(input.terminalState ?? '')) {
      throw new Error('Terminal observation requires authoritative server state');
    }
    return this.update(payload => {
      const record = payload.records.find(r =>
        r.operationId === token.operationId && r.consumerId === token.consumerId &&
        r.incarnation === token.incarnation,
      );
      if (!record || record.status === 'dismissed' ||
          record.status === 'terminal_observed') return null;
      const cursor = input.cursor ?? record.cursor;
      // Ignore regressed confirmations, never move the durable replay cursor back.
      if (cursor < record.cursor) return clone(record);
      record.cursor = cursor;
      record.lastSeenAt = Math.max(record.lastSeenAt, now);
      record.nextCheckAt = due;
      record.status = input.phase;
      record.failures = input.phase === 'disconnected'
        ? Math.min(1000, record.failures + 1) : 0;
      record.terminalState = input.phase === 'terminal_observed'
        ? input.terminalState! : null;
      return clone(record);
    });
  }
  async dismiss(token: Pick<MonthCycleRecord, 'operationId' | 'consumerId' | 'incarnation'>,
    now = Date.now()): Promise<boolean> {
    const at = time(now);
    return this.update(payload => {
      const r = payload.records.find(x => x.operationId === token.operationId &&
        x.consumerId === token.consumerId && x.incarnation === token.incarnation);
      if (!r || r.status === 'dismissed') return false;
      r.status = 'dismissed';
      r.lastSeenAt = Math.max(at, r.lastSeenAt);
      return true;
    });
  }
  async due(now = Date.now(), limit = 32): Promise<MonthCycleRecord[]> {
    const at = time(now);
    const max = Number.isSafeInteger(limit) ? Math.max(1, Math.min(32, limit)) : 32;
    return (await this.inspect())
      .filter(r => (r.status === 'observing' || r.status === 'disconnected') &&
        r.nextCheckAt <= at)
      .sort((a, b) => a.nextCheckAt - b.nextCheckAt || a.firstSeenAt - b.firstSeenAt)
      .slice(0, max);
  }
  async prune(now = Date.now()): Promise<number> {
    const at = time(now);
    return this.update(payload => {
      const count = payload.records.length;
      payload.records = payload.records.filter(r =>
        (r.status !== 'terminal_observed' && r.status !== 'dismissed') ||
        r.lastSeenAt > at || at - r.lastSeenAt < RETAIN_TERMINAL_MS);
      return count - payload.records.length;
    });
  }
}

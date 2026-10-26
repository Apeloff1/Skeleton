/** Owner-scoped client observation receipt. The backend alone owns job state. */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { getAuthEpoch, resolveStorageTenantIdentity, subscribeAuthChanges } from '../auth/gameforgeAuth';
import { OrderedCommitQueue } from '../utils/OrderedCommitQueue';

export type PlayableJobObservation = {
  jobId: string;
  kind?: string;
  playableId?: string;
  engineRequestKey?: string;
  errorCode?: string;
};

export interface PlayableJobObservationStore {
  get(): Promise<PlayableJobObservation | null>;
  set(record: PlayableJobObservation): Promise<void>;
  clear(jobId: string): Promise<boolean>;
  current(): boolean;
  dispose(): void;
}

const PREFIX = 'playable-job-observation:v1:';
const STORAGE_DEADLINE_MS = 3000;
const MAX_RECORD_CHARS = 2048;
const MAX_OWNER_QUEUES = 64;
const MAX_QUEUED_PER_OWNER = 16;
type QueueEntry = { queue: OrderedCommitQueue; pending: number };
const ownerQueues = new Map<string, QueueEntry>();
const jobId = (value: unknown): value is string => typeof value === 'string' && /^[A-Za-z0-9_-]{1,128}$/.test(value);
const kind = (value: unknown): value is string => typeof value === 'string' && /^[A-Za-z0-9_.:-]{1,64}$/.test(value);
const engineKey = (value: unknown): value is string => typeof value === 'string' && /^[A-Za-z0-9_.:/-]{1,256}$/.test(value);
const errorCode = (value: unknown): value is string => typeof value === 'string' && /^[A-Za-z0-9_.:-]{1,128}$/.test(value);
function object(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}
function record(value: unknown): PlayableJobObservation {
  if (!object(value) || !jobId(value.jobId)
    || Object.keys(value).some(key => !['jobId', 'kind', 'playableId', 'engineRequestKey', 'errorCode'].includes(key))
    || value.kind !== undefined && !kind(value.kind)
    || value.playableId !== undefined && !jobId(value.playableId)
    || value.engineRequestKey !== undefined && !engineKey(value.engineRequestKey)
    || value.errorCode !== undefined && !errorCode(value.errorCode)) {
    throw new Error('The retained playable job reference is invalid.');
  }
  return { jobId: value.jobId,
    ...(value.kind === undefined ? {} : { kind: value.kind }),
    ...(value.playableId === undefined ? {} : { playableId: value.playableId }),
    ...(value.engineRequestKey === undefined ? {} : { engineRequestKey: value.engineRequestKey }),
    ...(value.errorCode === undefined ? {} : { errorCode: value.errorCode }) };
}
function decode(raw: string | null): PlayableJobObservation | null {
  if (raw === null) return null;
  try {
    if (!raw || raw.length > MAX_RECORD_CHARS) throw new Error();
    const value: unknown = JSON.parse(raw);
    if (!object(value) || value.schema_version !== 1
      || Object.keys(value).some(key => !['schema_version', 'record'].includes(key))) throw new Error();
    return record(value.record);
  } catch { throw new Error('The saved playable job reference could not be verified. It has not been discarded.'); }
}

/** One logical read/modify/write sequence per owner in this JS runtime. Physical
 * writes retain queue custody even if cancellation/deadline ends the UI wait. */
function ordered<T>(key: string, operation: () => Promise<T>): Promise<T> {
  let entry = ownerQueues.get(key);
  if (!entry) {
    if (ownerQueues.size >= MAX_OWNER_QUEUES) return Promise.reject(new Error('Playable observation storage is busy.'));
    entry = { queue: new OrderedCommitQueue(), pending: 0 }; ownerQueues.set(key, entry);
  }
  if (entry.pending >= MAX_QUEUED_PER_OWNER) return Promise.reject(new Error('Playable observation storage is busy.'));
  entry.pending++;
  const captured = entry;
  const work = captured.queue.enqueue(operation);
  const release = () => {
    captured.pending--;
    if (captured.pending === 0 && ownerQueues.get(key) === captured) ownerQueues.delete(key);
  };
  void work.then(release, release);
  return work;
}

function observed<T>(work: Promise<T>, signal: AbortSignal, milliseconds: number): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    let settled = false;
    const finish = (value: T | Error, failed: boolean) => {
      if (settled) return;
      settled = true; clearTimeout(timer); signal.removeEventListener('abort', abort);
      if (failed) reject(value); else resolve(value as T);
    };
    const abort = () => finish(new Error('Playable observation account changed or monitoring was cancelled.'), true);
    const timer = setTimeout(() => finish(new Error('Playable job retention was not confirmed. Keep the original job reference and retry observation.'), true), milliseconds);
    signal.addEventListener('abort', abort, { once: true });
    void work.then(value => finish(value, false), () => finish(new Error('Playable job retention could not be verified. Keep the original job reference.'), true));
    if (signal.aborted) abort();
  });
}

export async function openPlayableJobObservation(signal?: AbortSignal): Promise<PlayableJobObservationStore> {
  const epoch = getAuthEpoch();
  const controller = new AbortController();
  const abort = () => controller.abort();
  const unsubscribe = subscribeAuthChanges(abort);
  signal?.addEventListener('abort', abort, { once: true });
  if (signal?.aborted) abort();
  const current = () => !controller.signal.aborted && epoch === getAuthEpoch();
  const assertCurrent = () => { if (!current()) throw new Error('Playable observation account changed or monitoring was cancelled.'); };
  const dispose = () => { abort(); unsubscribe(); signal?.removeEventListener('abort', abort); };
  try {
    assertCurrent();
    const identity = await observed(resolveStorageTenantIdentity(), controller.signal, 12000);
    assertCurrent();
    const validIdentity = (value: unknown): value is string => typeof value === 'string' && value.length > 0
      && value.length <= 512 && value === value.trim() && !/[\u0000-\u001f\u007f]/.test(value);
    if (!validIdentity(identity.tenantId) || !validIdentity(identity.principalId) || identity.principalId === 'anonymous') {
      throw new Error('Sign in to retain and resume your playable job.');
    }
    const key = PREFIX + encodeURIComponent(identity.tenantId) + ':' + encodeURIComponent(identity.principalId);
    const read = async () => { assertCurrent(); const raw = await AsyncStorage.getItem(key); assertCurrent(); return decode(raw); };
    const commit = <T>(operation: () => Promise<T>) => {
      assertCurrent();
      return observed(ordered(key, async () => { assertCurrent(); return operation(); }), controller.signal, STORAGE_DEADLINE_MS);
    };
    return {
      current, dispose,
      get: async () => commit(read),
      set: async value => {
        // Snapshot/validate before enqueueing: caller mutation cannot redirect
        // a delayed commit or sneak prompts/credentials into this receipt.
        const next = record(value), encoded = JSON.stringify({ schema_version: 1, record: next });
        return commit(async () => {
          const previous = await read();
          if (previous && previous.jobId !== next.jobId) throw new Error('Another playable job is retained. Dismiss that observation explicitly first.');
          assertCurrent(); await AsyncStorage.setItem(key, encoded); assertCurrent();
          const confirmed = await AsyncStorage.getItem(key); assertCurrent();
          if (confirmed !== encoded) throw new Error('Playable job retention failed verification.');
        });
      },
      clear: async id => {
        if (!jobId(id)) return Promise.reject(new Error('The playable job identity is invalid.'));
        return commit(async () => {
          const previous = await read();
          if (!previous || previous.jobId !== id) return false;
          assertCurrent(); await AsyncStorage.removeItem(key); assertCurrent();
          const confirmed = await AsyncStorage.getItem(key); assertCurrent();
          if (confirmed !== null) throw new Error('Playable observation dismissal failed verification.');
          return true;
        });
      },
    };
  } catch (error) { dispose(); throw error; }
}

/** An unconfirmed model execution is a retained observation, never a failure,
 * success, replay grant or instruction to submit another generation request. */
export function playableJobUnconfirmed(result: unknown): { engineRequestKey?: string; errorCode?: string } | null {
  if (!object(result) || result.ok === false) return null;
  const data = result.data === undefined ? result : result.data;
  if (!object(data) || data.job_status !== 'unconfirmed') return null;
  return {
    ...(engineKey(data.engine_request_key) ? { engineRequestKey: data.engine_request_key } : {}),
    ...(errorCode(data.error_code) ? { errorCode: data.error_code } : {}),
  };
}

/** One-time, account-scoped offline creator handoff.
 * Writes and consumes are serialized per scoped key within the same JS runtime.
 * No cross-device/process CAS is claimed. Never migrate unscoped records.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { CREATOR_BRIDGE_SCHEMA, CREATOR_BRIDGE_MAX_CHARS, parseCreatorBridge, type CreatorBridgeDraft, type CreatorBridgeTarget } from './creatorBridge';
import { getAuthEpoch } from '../auth/gameforgeAuth';
import { creatorStorageScope } from './creatorStorageScope';

const KEY = '@skeleton_creator_bridge_v1';

// AsyncStorage offers get/remove but no atomic consume. An in-process serial
// queue prevents two concurrent components from both claiming one handoff.
// The tail only holds completion signals, never user draft contents.
const locks = new Map<string, Promise<void>>();
async function serializeKey<T>(key: string, task: () => Promise<T>): Promise<T> {
  const prior = locks.get(key) ?? Promise.resolve();
  let release!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  const tail = prior.then(() => gate);
  locks.set(key, tail);
  await prior;
  try {
    return await task();
  } finally {
    release();
    if (locks.get(key) === tail) locks.delete(key);
  }
}

export async function storeCreatorBridge(draft: CreatorBridgeDraft, expectedEpoch: number = getAuthEpoch()): Promise<void> {
  if (getAuthEpoch() !== expectedEpoch) throw new Error('Stale creator editor');
  const valid = parseCreatorBridge(draft, draft.target);
  if (!valid) throw new Error('Invalid or expired creator bridge');
  const encoded = JSON.stringify(valid);
  if (encoded.length > CREATOR_BRIDGE_MAX_CHARS) throw new Error('Creator handoff exceeds storage limit');
  if (getAuthEpoch() !== expectedEpoch) throw new Error('Stale creator editor');
  const scope = await creatorStorageScope(KEY);
  if (getAuthEpoch() !== expectedEpoch) throw new Error('Creator account changed before storage');
  return serializeKey(scope.key, async () => {
    if (!scope.stillCurrent() || getAuthEpoch() !== expectedEpoch) throw new Error('Account changed before handoff');
    const previous = await AsyncStorage.getItem(scope.key);
    if (!scope.stillCurrent()) throw new Error('Account changed before handoff publication');
    await AsyncStorage.setItem(scope.key, encoded);
    if (!scope.stillCurrent()) {
      if (await AsyncStorage.getItem(scope.key) === encoded && previous !== encoded) {
        if (previous === null) await AsyncStorage.removeItem(scope.key);
        else await AsyncStorage.setItem(scope.key, previous);
      }
      throw new Error('Account changed while saving the creator handoff');
    }
  });
}

/** Delete only the observed envelope under the same-runtime key queue.
 * Cross-process CAS is not provided by AsyncStorage.
 */
async function removeObserved(
  key: string, raw: string, stillCurrent: () => boolean, restoreOnStale: boolean,
): Promise<void> {
  if (!stillCurrent()) throw new Error('Account changed before creator handoff cleanup');
  const current = await AsyncStorage.getItem(key);
  if (!stillCurrent()) throw new Error('Account changed during creator handoff cleanup');
  if (current !== raw) throw new Error('Creator handoff changed during publication');
  await AsyncStorage.removeItem(key);
  if (!stillCurrent()) {
    if (restoreOnStale && await AsyncStorage.getItem(key) === null) {
      await AsyncStorage.setItem(key, raw);
    }
    throw new Error('Account changed after creator handoff removal');
  }
}

/**
 * Transactional Studio return: verify the source-bound draft and persist the
 * receiving Studio project before acknowledging/removing the handoff.
 *
 * The caller's commit must be scoped to the same account epoch. If the
 * project save, validation or auth fence fails, the old owner's handoff
 * remains in its original namespace; it is never reissued to the newly
 * signed-in account. A second consumer in this JS runtime cannot claim the
 * same envelope while the callback is in progress.
 */
export async function withCreatorBridge<T>(
  target: CreatorBridgeTarget,
  commit: (draft: CreatorBridgeDraft) => Promise<T>,
  expectedEpoch: number = getAuthEpoch(),
): Promise<T | null> {
  if (getAuthEpoch() !== expectedEpoch) throw new Error('Account changed before Studio handoff scope');
  const scope = await creatorStorageScope(KEY);
  if (getAuthEpoch() !== expectedEpoch) throw new Error('Account changed during Studio handoff scope');
  return serializeKey(scope.key, async () => {
    if (getAuthEpoch() !== expectedEpoch || !scope.stillCurrent()) throw new Error('Account changed before Studio handoff read');
    const raw = await AsyncStorage.getItem(scope.key);
    if (!scope.stillCurrent()) throw new Error('Account changed during Studio handoff read');
    if (!raw) return null;
    if (raw.length > CREATOR_BRIDGE_MAX_CHARS) {
      await removeObserved(scope.key, raw, scope.stillCurrent, false);
      return null;
    }
    let parsed: unknown;
    try { parsed = JSON.parse(raw); }
    catch { await removeObserved(scope.key, raw, scope.stillCurrent, false); return null; }
    const envelope = parsed !== null && typeof parsed === 'object' && !Array.isArray(parsed)
      ? parsed as Record<string, unknown> : null;
    if (!envelope || envelope.schema !== CREATOR_BRIDGE_SCHEMA) {
      await removeObserved(scope.key, raw, scope.stillCurrent, false);
      return null;
    }
    if (envelope.target !== target) return null;
    const draft = parseCreatorBridge(parsed, target);
    if (!draft) {
      await removeObserved(scope.key, raw, scope.stillCurrent, false);
      return null;
    }
    // The callback must either complete the receiving-project write, or
    // fail without consuming this one-time private handoff.
    const applied = await commit(draft);
    if (!scope.stillCurrent()) throw new Error('Account changed before Studio handoff acknowledgement');
    // The receiving project is already committed; do not resurrect it.
    await removeObserved(scope.key, raw, scope.stillCurrent, false);
    return applied;
  });
}

export async function consumeCreatorBridge(
  target: CreatorBridgeTarget, expectedEpoch: number = getAuthEpoch(),
  receiverCurrent: () => boolean = () => true,
): Promise<CreatorBridgeDraft | null> {
  const epochCurrent = () => getAuthEpoch() === expectedEpoch && receiverCurrent();
  if (!epochCurrent()) throw new Error('Account changed or creator receiver superseded before handoff scope');
  const scope = await creatorStorageScope(KEY);
  if (!epochCurrent()) throw new Error('Account changed or creator receiver superseded during handoff scope');
  const current = () => epochCurrent() && scope.stillCurrent();
  return serializeKey(scope.key, async () => {
    if (!current()) throw new Error('Account changed or creator receiver superseded before reading handoff');
    const raw = await AsyncStorage.getItem(scope.key);
    if (!current()) throw new Error('Account changed or creator receiver superseded while reading handoff');
    if (!raw || raw.length > CREATOR_BRIDGE_MAX_CHARS) {
      if (raw) await removeObserved(scope.key, raw, current, false);
      return null;
    }
    let parsed: unknown;
    try { parsed = JSON.parse(raw); }
    catch { await removeObserved(scope.key, raw, current, false); return null; }
    const envelope = parsed !== null && typeof parsed === 'object' && !Array.isArray(parsed)
      ? parsed as Record<string, unknown> : null;
    if (!envelope || envelope.schema !== CREATOR_BRIDGE_SCHEMA) {
      await removeObserved(scope.key, raw, current, false);
      return null;
    }
    // A wrong-direction reader must not consume someone else's valid handoff.
    if (envelope.target !== target) return null;
    const valid = parseCreatorBridge(parsed, target);
    await removeObserved(scope.key, raw, current, valid !== null);
    return valid;
  });
}

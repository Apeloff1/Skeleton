/** One-time, account-scoped offline creator handoff.
 * Writes and consumes are serialized per scoped key within the same JS runtime.
 * No cross-device/process CAS is claimed. Never migrate unscoped records.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { CREATOR_BRIDGE_SCHEMA, parseCreatorBridge, type CreatorBridgeDraft, type CreatorBridgeTarget } from './creatorBridge';
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

export async function storeCreatorBridge(draft: CreatorBridgeDraft): Promise<void> {
  const valid = parseCreatorBridge(draft, draft.target);
  if (!valid) throw new Error('Invalid or expired creator bridge');
  const scope = await creatorStorageScope(KEY);
  return serializeKey(scope.key, async () => {
    if (!scope.stillCurrent()) throw new Error('Account changed before handoff');
    await AsyncStorage.setItem(scope.key, JSON.stringify(valid));
    if (!scope.stillCurrent()) {
      await AsyncStorage.removeItem(scope.key);
      throw new Error('Account changed while saving the creator handoff');
    }
  });
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
): Promise<T | null> {
  const scope = await creatorStorageScope(KEY);
  return serializeKey(scope.key, async () => {
    if (!scope.stillCurrent()) throw new Error('Account changed before Studio handoff read');
    const raw = await AsyncStorage.getItem(scope.key);
    if (!scope.stillCurrent()) throw new Error('Account changed during Studio handoff read');
    if (!raw) return null;
    if (raw.length > 16_384) {
      await AsyncStorage.removeItem(scope.key);
      return null;
    }
    let parsed: unknown;
    try { parsed = JSON.parse(raw); }
    catch { await AsyncStorage.removeItem(scope.key); return null; }
    const envelope = parsed !== null && typeof parsed === 'object' && !Array.isArray(parsed)
      ? parsed as Record<string, unknown> : null;
    if (!envelope || envelope.schema !== CREATOR_BRIDGE_SCHEMA) {
      await AsyncStorage.removeItem(scope.key);
      return null;
    }
    if (envelope.target !== target) return null;
    const draft = parseCreatorBridge(parsed, target);
    if (!draft) {
      await AsyncStorage.removeItem(scope.key);
      return null;
    }
    // The callback must either complete the receiving-project write, or
    // fail without consuming this one-time private handoff.
    const applied = await commit(draft);
    if (!scope.stillCurrent()) throw new Error('Account changed before Studio handoff acknowledgement');
    const current = await AsyncStorage.getItem(scope.key);
    if (!scope.stillCurrent()) throw new Error('Account changed while acknowledging Studio handoff');
    if (current !== raw) throw new Error('Studio handoff changed during publication');
    await AsyncStorage.removeItem(scope.key);
    if (!scope.stillCurrent()) throw new Error('Account changed after Studio handoff acknowledgement');
    return applied;
  });
}

export async function consumeCreatorBridge(target: CreatorBridgeTarget): Promise<CreatorBridgeDraft | null> {
  const scope = await creatorStorageScope(KEY);
  return serializeKey(scope.key, async () => {
    if (!scope.stillCurrent()) throw new Error('Account changed before reading creator handoff');
    const raw = await AsyncStorage.getItem(scope.key);
    if (!scope.stillCurrent()) throw new Error('Account changed while reading the creator handoff');
    if (!raw || raw.length > 16_384) {
      if (raw) await AsyncStorage.removeItem(scope.key);
      return null;
    }
    let parsed: unknown;
    try { parsed = JSON.parse(raw); }
    catch { await AsyncStorage.removeItem(scope.key); return null; }
    const envelope = parsed !== null && typeof parsed === 'object' && !Array.isArray(parsed)
      ? parsed as Record<string, unknown> : null;
    if (!envelope || envelope.schema !== CREATOR_BRIDGE_SCHEMA) {
      await AsyncStorage.removeItem(scope.key);
      return null;
    }
    // A wrong-direction reader must not consume someone else's valid handoff.
    if (envelope.target !== target) return null;
    const valid = parseCreatorBridge(parsed, target);
    await AsyncStorage.removeItem(scope.key);
    if (!scope.stillCurrent()) throw new Error('Account changed before applying the creator handoff');
    return valid;
  });
}

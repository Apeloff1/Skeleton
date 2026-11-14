/** One-time, account-scoped offline creator handoff.
 * Writes and consumes are serialized per scoped key within the same JS runtime.
 * No cross-device/process CAS is claimed. Never migrate unscoped records.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { CREATOR_BRIDGE_SCHEMA, parseCreatorBridge, type CreatorBridgeDraft, type CreatorBridgeTarget } from './creatorBridge';
import { MAX_PROFILE_CHARS } from './galaxyHandoff';
import { creatorStorageScope } from './creatorStorageScope';

const KEY = '@skeleton_creator_bridge_v1';
const MAX_BRIDGE_BYTES = MAX_PROFILE_CHARS + 24_000;

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
  const data = JSON.stringify(valid);
  if (data.length > MAX_BRIDGE_BYTES) throw new Error('Creator handoff exceeds bounded storage budget');
  return serializeKey(scope.key, async () => {
    if (!scope.stillCurrent()) throw new Error('Account changed before handoff');
    await AsyncStorage.setItem(scope.key, data);
    if (!scope.stillCurrent()) {
      await AsyncStorage.removeItem(scope.key);
      throw new Error('Account changed while saving the creator handoff');
    }
  });
}

export async function consumeCreatorBridge(target: CreatorBridgeTarget): Promise<CreatorBridgeDraft | null> {
  const scope = await creatorStorageScope(KEY);
  return serializeKey(scope.key, async () => {
    if (!scope.stillCurrent()) throw new Error('Account changed before reading creator handoff');
    const raw = await AsyncStorage.getItem(scope.key);
    if (!scope.stillCurrent()) throw new Error('Account changed while reading the creator handoff');
    if (!raw || raw.length > MAX_BRIDGE_BYTES) {
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

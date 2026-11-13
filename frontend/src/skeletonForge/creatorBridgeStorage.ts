/** Single-use, owner-scoped offline handoff with account-change fences.
 * A short-lived validated message is deliberately not migrated from old
 * unscoped storage keys, which could leak a different local user's draft.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { CREATOR_BRIDGE_SCHEMA, parseCreatorBridge, type CreatorBridgeDraft, type CreatorBridgeTarget } from './creatorBridge';
import { creatorStorageScope } from './creatorStorageScope';

const KEY = '@skeleton_creator_bridge_v1';

export async function storeCreatorBridge(draft: CreatorBridgeDraft): Promise<void> {
  const valid = parseCreatorBridge(draft, draft.target);
  if (!valid) throw new Error('Invalid or expired creator bridge');
  const scope = await creatorStorageScope(KEY);
  if (!scope.stillCurrent()) throw new Error('Account changed before handoff');
  await AsyncStorage.setItem(scope.key, JSON.stringify(valid));
  if (!scope.stillCurrent()) {
    await AsyncStorage.removeItem(scope.key);
    throw new Error('Account changed while saving the creator handoff');
  }
}

export async function consumeCreatorBridge(target: CreatorBridgeTarget): Promise<CreatorBridgeDraft | null> {
  const scope = await creatorStorageScope(KEY);
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
  if (envelope.target !== target) return null;
  const valid = parseCreatorBridge(parsed, target);
  await AsyncStorage.removeItem(scope.key);
  if (!scope.stillCurrent()) throw new Error('Account changed before applying the creator handoff');
  return valid;
}

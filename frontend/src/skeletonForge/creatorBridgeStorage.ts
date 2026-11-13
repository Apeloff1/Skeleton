/** Device-local, single-use opt-in creator draft bridge. Nothing is uploaded.
 * Do not import this IO module into pure-node questionnaire tests.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { CREATOR_BRIDGE_SCHEMA, parseCreatorBridge, type CreatorBridgeDraft, type CreatorBridgeTarget } from './creatorBridge';

const KEY = '@skeleton_creator_bridge_v1';

export async function storeCreatorBridge(draft: CreatorBridgeDraft): Promise<void> {
  const valid = parseCreatorBridge(draft, draft.target);
  if (!valid) throw new Error('Invalid or expired creator bridge');
  await AsyncStorage.setItem(KEY, JSON.stringify(valid));
}

export async function consumeCreatorBridge(target: CreatorBridgeTarget): Promise<CreatorBridgeDraft | null> {
  const raw = await AsyncStorage.getItem(KEY);
  if (!raw || raw.length > 16_384) {
    if (raw) await AsyncStorage.removeItem(KEY);
    return null;
  }
  let parsed: unknown;
  try { parsed = JSON.parse(raw); }
  catch { await AsyncStorage.removeItem(KEY); return null; }
  const envelope = parsed !== null && typeof parsed === 'object' && !Array.isArray(parsed)
    ? parsed as Record<string, unknown> : null;
  if (!envelope || envelope.schema !== CREATOR_BRIDGE_SCHEMA) {
    await AsyncStorage.removeItem(KEY);
    return null;
  }
  if (envelope.target !== target) return null;
  const valid = parseCreatorBridge(parsed, target);
  await AsyncStorage.removeItem(KEY);
  return valid;
}

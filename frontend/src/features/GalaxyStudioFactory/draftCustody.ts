/** Explicit device-local Galaxy draft storage, separate from the Forge handoff. */
import AsyncStorage from '@react-native-async-storage/async-storage';
import {
  GALAXY_DRAFT_MAX_BYTES, normalizeGalaxyDraft,
  type GalaxyDraftSnapshot,
} from './galaxyDraftCodec';
export { GALAXY_DRAFT_SCHEMA, type GalaxyDraftSnapshot } from './galaxyDraftCodec';
const KEY = '@skeleton_galaxy_editor_draft_v1';

export async function saveGalaxyDraft(raw: GalaxyDraftSnapshot): Promise<void> {
  const clean = normalizeGalaxyDraft(raw);
  if (!clean) throw new Error('Invalid Galaxy studio draft');
  const data = JSON.stringify(clean);
  if (data.length > GALAXY_DRAFT_MAX_BYTES) throw new Error('Galaxy editor draft exceeds local storage policy');
  await AsyncStorage.setItem(KEY, data);
}

export async function loadGalaxyDraft(): Promise<GalaxyDraftSnapshot | null> {
  const content = await AsyncStorage.getItem(KEY);
  if (!content) return null;
  if (content.length > GALAXY_DRAFT_MAX_BYTES) {
    await AsyncStorage.removeItem(KEY);
    return null;
  }
  try {
    const normalized = normalizeGalaxyDraft(JSON.parse(content));
    if (!normalized) await AsyncStorage.removeItem(KEY);
    return normalized;
  } catch {
    await AsyncStorage.removeItem(KEY);
    return null;
  }
}

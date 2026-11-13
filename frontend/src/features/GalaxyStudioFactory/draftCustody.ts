/** Offline, per-account Galaxy design custody; bearer token never stored here. */
import AsyncStorage from '@react-native-async-storage/async-storage';
import {
  GALAXY_DRAFT_MAX_BYTES, normalizeGalaxyDraft,
  type GalaxyDraftSnapshot,
} from './galaxyDraftCodec';
import { creatorStorageScope } from '../../skeletonForge/creatorStorageScope';

export { GALAXY_DRAFT_SCHEMA, type GalaxyDraftSnapshot } from './galaxyDraftCodec';
const KEY = '@skeleton_galaxy_editor_draft_v1';

export async function saveGalaxyDraft(raw: GalaxyDraftSnapshot): Promise<void> {
  const clean = normalizeGalaxyDraft(raw);
  if (!clean) throw new Error('Invalid Galaxy studio draft');
  const data = JSON.stringify(clean);
  if (data.length > GALAXY_DRAFT_MAX_BYTES) throw new Error('Galaxy editor draft exceeds local storage policy');
  const scope = await creatorStorageScope(KEY);
  if (!scope.stillCurrent()) throw new Error('Account changed before saving Galaxy draft');
  await AsyncStorage.setItem(scope.key, data);
  if (!scope.stillCurrent()) {
    await AsyncStorage.removeItem(scope.key);
    throw new Error('Account changed while saving Galaxy draft');
  }
}

export async function loadGalaxyDraft(): Promise<GalaxyDraftSnapshot | null> {
  const scope = await creatorStorageScope(KEY);
  const content = await AsyncStorage.getItem(scope.key);
  if (!scope.stillCurrent()) throw new Error('Account changed while reading Galaxy draft');
  if (!content) return null;
  if (content.length > GALAXY_DRAFT_MAX_BYTES) {
    await AsyncStorage.removeItem(scope.key);
    return null;
  }
  try {
    const normalized = normalizeGalaxyDraft(JSON.parse(content));
    if (!normalized) await AsyncStorage.removeItem(scope.key);
    if (!scope.stillCurrent()) throw new Error('Account changed before restoring Galaxy draft');
    return normalized;
  } catch (error) {
    // Retain the epoch failure instead of silently swallowing account changes.
    if (!scope.stillCurrent()) throw error;
    await AsyncStorage.removeItem(scope.key);
    return null;
  }
}

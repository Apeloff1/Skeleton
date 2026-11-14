/** Opt-in local Galaxy profile snapshots; no network or provider access.
 * Scope ties the saved design to the current token fingerprint/epoch;
 * AsyncStorage is local storage, not encrypted storage or an auth boundary.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { creatorStorageScope } from './creatorStorageScope';
import {
  SAVED_GALAXY_MAX_CHARS, makeSavedGalaxyProfile, parseSavedGalaxyProfile,
} from './galaxyProfileSnapshot';
import type { GalaxyProfile } from './galaxyHandoff';

const KEY = '@skeleton_galaxy_profile_snapshot_v1';

export async function saveGalaxyProfile(payload: unknown): Promise<void> {
  const data = JSON.stringify(makeSavedGalaxyProfile(payload));
  if (data.length > SAVED_GALAXY_MAX_CHARS) throw new Error('Galaxy profile exceeds storage budget');
  const scope = await creatorStorageScope(KEY);
  if (!scope.stillCurrent()) throw new Error('Account changed before Galaxy save');
  await AsyncStorage.setItem(scope.key, data);
  if (!scope.stillCurrent()) {
    await AsyncStorage.removeItem(scope.key);
    throw new Error('Account changed during Galaxy save');
  }
}
export async function loadGalaxyProfile(): Promise<GalaxyProfile | null> {
  const scope = await creatorStorageScope(KEY);
  const raw = await AsyncStorage.getItem(scope.key);
  if (!scope.stillCurrent()) throw new Error('Account changed during Galaxy load');
  if (!raw) return null;
  if (raw.length > SAVED_GALAXY_MAX_CHARS) {
    await AsyncStorage.removeItem(scope.key);
    return null;
  }
  let parsed: unknown;
  try { parsed = JSON.parse(raw); }
  catch { await AsyncStorage.removeItem(scope.key); return null; }
  const saved = parseSavedGalaxyProfile(parsed);
  if (!saved) {
    await AsyncStorage.removeItem(scope.key);
    return null;
  }
  if (!scope.stillCurrent()) throw new Error('Account changed before applying Galaxy draft');
  return saved.profile;
}
export async function clearSavedGalaxyProfile(): Promise<void> {
  const scope = await creatorStorageScope(KEY);
  if (!scope.stillCurrent()) throw new Error('Account changed before clearing Galaxy draft');
  await AsyncStorage.removeItem(scope.key);
  if (!scope.stillCurrent()) throw new Error('Account changed while clearing Galaxy draft');
}

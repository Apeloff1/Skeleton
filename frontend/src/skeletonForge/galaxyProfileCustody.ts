/** Opt-in local Galaxy profile snapshots; no network or provider access.
 * Scope ties the saved design to the current token fingerprint/epoch;
 * AsyncStorage is local storage, not encrypted storage or an auth boundary.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { creatorStorageScope } from './creatorStorageScope';
import { getAuthEpoch } from '../auth/gameforgeAuth';
import {
  SAVED_GALAXY_MAX_CHARS, makeSavedGalaxyProfile, parseSavedGalaxyProfile,
} from './galaxyProfileSnapshot';
import type { GalaxyProfile } from './galaxyHandoff';

const KEY = '@skeleton_galaxy_profile_snapshot_v1';

const tails = new Map<string, Promise<void>>();

async function serialize<T>(key: string, task: () => Promise<T>): Promise<T> {
  const prior = tails.get(key) ?? Promise.resolve();
  const result = prior.then(task);
  const tail = result.then(() => {}, () => {});
  tails.set(key, tail);
  void tail.then(() => { if (tails.get(key) === tail) tails.delete(key); });
  return result;
}

async function ownerScope(expectedEpoch: number) {
  if (getAuthEpoch() !== expectedEpoch) throw new Error('Stale Galaxy profile editor');
  const scope = await creatorStorageScope(KEY);
  const requireOwner = () => {
    if (getAuthEpoch() !== expectedEpoch || !scope.stillCurrent())
      throw new Error('Account changed during Galaxy profile operation');
  };
  requireOwner();
  return { key: scope.key, requireOwner };
}

export async function saveGalaxyProfile(payload: unknown, expectedEpoch = getAuthEpoch()): Promise<void> {
  const data = JSON.stringify(makeSavedGalaxyProfile(payload));
  if (data.length > SAVED_GALAXY_MAX_CHARS) throw new Error('Galaxy profile exceeds storage budget');
  const scope = await ownerScope(expectedEpoch);
  await serialize(scope.key, async () => {
    scope.requireOwner();
    const previous = await AsyncStorage.getItem(scope.key);
    scope.requireOwner();
    await AsyncStorage.setItem(scope.key, data);
    try { scope.requireOwner(); }
    catch (error) {
      // Roll back this publication only; all same-runtime profile operations
      // for this exact owner namespace are serialized.
      // Do not overwrite a newer publication from another storage owner.
      // AsyncStorage has no cross-process compare-and-swap; this is a
      // best-effort rollback constrained to the value just published.
      if (await AsyncStorage.getItem(scope.key) === data && previous !== data) {
        if (previous === null) await AsyncStorage.removeItem(scope.key);
        else await AsyncStorage.setItem(scope.key, previous);
      }
      throw error;
    }
  });
}

export async function loadGalaxyProfile(expectedEpoch = getAuthEpoch()): Promise<GalaxyProfile | null> {
  const scope = await ownerScope(expectedEpoch);
  return serialize(scope.key, async () => {
    scope.requireOwner();
    const raw = await AsyncStorage.getItem(scope.key);
    scope.requireOwner();
    if (!raw || raw.length > SAVED_GALAXY_MAX_CHARS) return null;
    let parsed: unknown;
    try { parsed = JSON.parse(raw); } catch { return null; }
    const saved = parseSavedGalaxyProfile(parsed);
    scope.requireOwner();
    return saved?.profile ?? null;
  });
}

export async function clearSavedGalaxyProfile(expectedEpoch = getAuthEpoch()): Promise<void> {
  const scope = await ownerScope(expectedEpoch);
  await serialize(scope.key, async () => {
    scope.requireOwner();
    const previous = await AsyncStorage.getItem(scope.key);
    scope.requireOwner();
    await AsyncStorage.removeItem(scope.key);
    try { scope.requireOwner(); }
    catch (error) {
      // A stale deletion must not silently erase that account's design.
      // Only restore if no replacement has appeared since the deletion.
      if (previous !== null && await AsyncStorage.getItem(scope.key) === null) {
        await AsyncStorage.setItem(scope.key, previous);
      }
      throw error;
    }
  });
}

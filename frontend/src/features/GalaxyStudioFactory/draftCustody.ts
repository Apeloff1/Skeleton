/** Offline, per-account Galaxy design custody; bearer token never stored here.
 * Serializes access per namespace in this JS runtime. AsyncStorage has no
 * cross-process compare-and-swap; do not claim multi-process transactions.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import {
  GALAXY_DRAFT_MAX_BYTES, normalizeGalaxyDraft,
  type GalaxyDraftSnapshot,
} from './galaxyDraftCodec';
import { creatorStorageScope } from '../../skeletonForge/creatorStorageScope';
import { getAuthEpoch } from '../../auth/gameforgeAuth';

export { GALAXY_DRAFT_SCHEMA, type GalaxyDraftSnapshot } from './galaxyDraftCodec';
const KEY = '@skeleton_galaxy_editor_draft_v1';
const tails = new Map<string, Promise<void>>();

async function serialize<T>(key: string, task: () => Promise<T>): Promise<T> {
  const previous = tails.get(key) ?? Promise.resolve();
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  const tail = previous.then(() => gate);
  tails.set(key, tail);
  await previous;
  try { return await task(); }
  finally {
    release();
    if (tails.get(key) === tail) tails.delete(key);
  }
}

export async function saveGalaxyDraft(raw: GalaxyDraftSnapshot, expectedEpoch: number = getAuthEpoch()): Promise<void> {
  if (getAuthEpoch() !== expectedEpoch) throw new Error('Stale Galaxy editor');
  const clean = normalizeGalaxyDraft(raw);
  if (!clean) throw new Error('Invalid Galaxy studio draft');
  const data = JSON.stringify(clean);
  if (data.length > GALAXY_DRAFT_MAX_BYTES) throw new Error('Galaxy editor draft exceeds local storage policy');
  const scope = await creatorStorageScope(KEY);
  const current = () => scope.stillCurrent() && getAuthEpoch() === expectedEpoch;
  return serialize(scope.key, async () => {
    if (!current()) throw new Error('Account changed before saving Galaxy draft');
    const previous = await AsyncStorage.getItem(scope.key);
    if (!current()) throw new Error('Account changed before saving Galaxy draft');
    await AsyncStorage.setItem(scope.key, data);
    if (!current()) {
      // Restore only this write's observed value in its original namespace.
      // AsyncStorage provides no cross-process compare-and-swap.
      const observed = await AsyncStorage.getItem(scope.key);
      if (observed === data && previous !== data) {
        if (previous === null) await AsyncStorage.removeItem(scope.key);
        else await AsyncStorage.setItem(scope.key, previous);
      }
      throw new Error('Account changed while saving Galaxy draft');
    }
  });
}

export async function loadGalaxyDraft(): Promise<GalaxyDraftSnapshot | null> {
  const expectedEpoch = getAuthEpoch();
  const scope = await creatorStorageScope(KEY);
  const current = () => scope.stillCurrent() && getAuthEpoch() === expectedEpoch;
  return serialize(scope.key, async () => {
    if (!current()) throw new Error('Account changed before reading Galaxy draft');
    const content = await AsyncStorage.getItem(scope.key);
    if (!current()) throw new Error('Account changed while reading Galaxy draft');
    if (!content) return null;
    let normalized: GalaxyDraftSnapshot | null = null;
    if (content.length <= GALAXY_DRAFT_MAX_BYTES) {
      try { normalized = normalizeGalaxyDraft(JSON.parse(content)); }
      catch { /* malformed or expired data follows the existing cleanup policy */ }
    }
    if (!current()) throw new Error('Account changed before restoring Galaxy draft');
    if (!normalized) {
      // Recheck the exact value before cleanup. In-process writers are
      // serialized; this is not a distributed CAS.
      const observed = await AsyncStorage.getItem(scope.key);
      if (!current()) throw new Error('Account changed before cleaning Galaxy draft');
      if (observed === content) await AsyncStorage.removeItem(scope.key);
      if (!current()) throw new Error('Account changed while cleaning Galaxy draft');
      return null;
    }
    return normalized;
  });
}

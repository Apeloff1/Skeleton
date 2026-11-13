/** Offline owner-scoped storage custody for private, user-authored game drafts.
 *
 * No backend lookup, remote provider, or network request. Derive a fixed-size
 * one-way fingerprint from the active locally-held bearer token; never write
 * the bearer itself to an AsyncStorage key. Empty authenticated state uses a
 * separate anonymous namespace. Auth epoch checks fence account rotation
 * during the asynchronous digest and storage operation.
 */
import * as Crypto from 'expo-crypto';
import { getAuthEpoch, getAuthToken, initializeStoredToken } from '../auth/gameforgeAuth';

const ALLOWED_PREFIXES = new Set([
  '@skeleton_creator_bridge_v1',
  '@skeleton_galaxy_editor_draft_v1',
  '@skeleton_galaxy_profile_snapshot_v1',
  // First-install Studio project records use the same owner-fenced storage
  // as Forge, without attributing old unscoped drafts to a new account.
  'skeleton.studio.onboarded.v1',
  'skeleton.studio.projects.v1',
  'skeleton.studio.prefs.v1',
]);

export interface CreatorStorageScope {
  key: string;
  /** Check immediately before publishing or returning data. */
  stillCurrent: () => boolean;
}

export async function creatorStorageScope(prefix: string): Promise<CreatorStorageScope> {
  if (!ALLOWED_PREFIXES.has(prefix)) throw new Error('Unrecognized creator storage namespace');
  await initializeStoredToken();
  const epoch = getAuthEpoch();
  const token = getAuthToken();
  const fingerprint = token
    ? await Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256, token)
    : 'anonymous';
  const stillCurrent = () => epoch === getAuthEpoch() && token === getAuthToken();
  if (!stillCurrent()) throw new Error('Account changed while creating game draft storage scope');
  if (!/^(?:anonymous|[a-fA-F0-9]{64})$/.test(fingerprint)) {
    throw new Error('Invalid creator storage fingerprint');
  }
  return { key: prefix + ':' + fingerprint.toLowerCase(), stillCurrent };
}

/**
 * Account-isolated AsyncStorage adapter for the first-install Studio shell.
 * Unscoped historical data is exposed read-only for *explicit* migration,
 * never automatically attributed to the currently authenticated account.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { creatorStorageScope, type CreatorStorageScope } from '../creatorStorageScope';
import { KEYS, type Kv } from './storage';

const KEY_SET = new Set<string>(Object.values(KEYS));

function allowed(key: string): void {
  if (!KEY_SET.has(key)) throw new Error('Unexpected first-install storage key');
}

/**
 * Bind *every* key in one Studio session to a single account snapshot.
 * Recomputing the token fingerprint for each setItem allowed a logout in
 * the middle of saveFoundation's three writes to publish an old user's
 * projects under the incoming user's key.
 *
 * The scope promise is lazy, shared by concurrent load requests and never
 * renegotiated after an auth epoch rotation. A new authenticated session
 * must create a new adapter; old adapters fail closed instead of rebinding.
 */
export function asyncStorageKv(): Kv {
  let owner: Promise<CreatorStorageScope> | null = null;
  const lockedScope = () => {
    if (!owner) owner = creatorStorageScope(KEYS.projects);
    return owner;
  };
  async function scopedKey(key: string): Promise<{ key: string; scope: CreatorStorageScope }> {
    allowed(key);
    const scope = await lockedScope();
    if (!scope.stillCurrent()) throw new Error('Account changed during Studio project storage');
    const prefix = KEYS.projects + ':';
    if (!scope.key.startsWith(prefix)) throw new Error('Invalid Studio project storage prefix');
    const fingerprint = scope.key.slice(prefix.length);
    if (!/^(?:anonymous|[a-f0-9]{64})$/.test(fingerprint)) {
      throw new Error('Invalid Studio project owner fingerprint');
    }
    return { key: key + ':' + fingerprint, scope };
  }
  return {
    async getItem(key) {
      const selected = await scopedKey(key);
      const content = await AsyncStorage.getItem(selected.key);
      if (!selected.scope.stillCurrent()) throw new Error('Account changed during Studio project read');
      return content;
    },
    async setItem(key, value) {
      const selected = await scopedKey(key);
      if (!selected.scope.stillCurrent()) throw new Error('Account changed before Studio project write');
      await AsyncStorage.setItem(selected.key, value);
      if (!selected.scope.stillCurrent()) throw new Error('Account changed during Studio project write');
    },
  };
}

/** Only detect whether a legacy unscoped blob exists; never expose its
 * content until a user explicitly selects Import Legacy Projects. */
export async function hasLegacyStudioProjects(): Promise<boolean> {
  const raw = await AsyncStorage.getItem(KEYS.projects);
  return typeof raw === 'string' && raw.length > 0;
}

/** Read-only legacy key adapter. It must never write to unscoped storage. */
export function legacyReadOnlyKv(): Kv {
  return {
    getItem(key) {
      allowed(key);
      return AsyncStorage.getItem(key);
    },
    async setItem() {
      throw new Error('Legacy Studio project storage is read-only');
    },
  };
}

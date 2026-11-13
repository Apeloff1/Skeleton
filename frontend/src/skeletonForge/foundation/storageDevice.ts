/**
 * Account-isolated AsyncStorage adapter for the first-install Studio shell.
 * Unscoped historical data is exposed read-only for *explicit* migration,
 * never automatically attributed to the currently authenticated account.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { creatorStorageScope } from '../creatorStorageScope';
import { KEYS, type Kv } from './storage';

const KEY_SET = new Set<string>(Object.values(KEYS));

function allowed(key: string): void {
  if (!KEY_SET.has(key)) throw new Error('Unexpected first-install storage key');
}

export function asyncStorageKv(): Kv {
  return {
    async getItem(key) {
      allowed(key);
      const scope = await creatorStorageScope(key);
      const content = await AsyncStorage.getItem(scope.key);
      if (!scope.stillCurrent()) throw new Error('Account changed during Studio project read');
      return content;
    },
    async setItem(key, value) {
      allowed(key);
      const scope = await creatorStorageScope(key);
      if (!scope.stillCurrent()) throw new Error('Account changed before Studio project write');
      await AsyncStorage.setItem(scope.key, value);
      if (!scope.stillCurrent()) throw new Error('Account changed during Studio project write');
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

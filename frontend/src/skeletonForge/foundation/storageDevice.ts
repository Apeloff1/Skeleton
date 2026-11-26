/**
 * Account-isolated AsyncStorage adapter for the first-install Studio shell.
 * Unscoped historical data is exposed read-only for *explicit* migration,
 * never automatically attributed to the currently authenticated account.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { getAuthEpoch } from '../../auth/gameforgeAuth';
import { creatorStorageScope, type CreatorStorageScope } from '../creatorStorageScope';
import { KEYS, type Kv } from './storage';

const KEY_SET = new Set<string>(Object.values(KEYS));
// All adapters sharing a resolved fingerprint also share the queue. A
// remount or account reentry cannot interleave a three-key publication
// with another adapter's read, rollback, or read/modify/write operation.
const namespaceTails = new Map<string, Promise<void>>();

async function serialize<T>(key: string, task: () => Promise<T>): Promise<T> {
  const prior = namespaceTails.get(key) ?? Promise.resolve();
  const result = prior.then(task);
  const tail = result.then(() => {}, () => {});
  namespaceTails.set(key, tail);
  void tail.then(() => {
    if (namespaceTails.get(key) === tail) namespaceTails.delete(key);
  });
  return result;
}

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
export function asyncStorageKv(expectedEpoch: number = getAuthEpoch()): Kv {
  let owner: Promise<CreatorStorageScope> | null = null;
  let observedProjects: string | null | undefined;
  const assertEpoch = () => {
    if (getAuthEpoch() !== expectedEpoch) throw new Error('Account changed during Studio project storage');
  };
  const lockedScope = () => {
    assertEpoch();
    if (!owner) {
      const candidate = creatorStorageScope(KEYS.projects);
      owner = candidate;
      // Only a *failed initial acquisition* is retryable. Once a real
      // fingerprint was captured, epoch rotation permanently fences this
      // adapter, even when the old bearer is restored.
      void candidate.catch(() => {
        if (owner === candidate) owner = null;
      });
    }
    return owner;
  };
  async function scopedKey(key: string): Promise<{ key: string; scope: CreatorStorageScope }> {
    allowed(key);
    const scope = await lockedScope();
    assertEpoch();
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
    async runExclusive<T>(task: () => Promise<T>, mode: 'read' | 'write' | 'refresh'): Promise<T> {
      const selected = await scopedKey(KEYS.projects);
      return serialize(selected.key, async () => {
        assertEpoch();
        if (!selected.scope.stillCurrent()) throw new Error('Account changed before Studio transaction');
        // Ordinary autosaves must not overwrite a different adapter's
        // completed project revision. Explicit refresh transactions first
        // load the current library and reconcile against that revision.
        if (mode === 'write' && observedProjects !== undefined) {
          const latest = await AsyncStorage.getItem(selected.key);
          assertEpoch();
          if (!selected.scope.stillCurrent()) throw new Error('Account changed before Studio publication');
          if (latest !== observedProjects) throw new Error('Studio project library changed; reload before saving');
        }
        const result = await task();
        assertEpoch();
        if (!selected.scope.stillCurrent()) throw new Error('Account changed during Studio transaction');
        return result;
      });
    },
    async getItem(key) {
      const selected = await scopedKey(key);
      const content = await AsyncStorage.getItem(selected.key);
      assertEpoch();
      if (!selected.scope.stillCurrent()) throw new Error('Account changed during Studio project read');
      if (key === KEYS.projects) observedProjects = content;
      return content;
    },
    async setItem(key, value) {
      const selected = await scopedKey(key);
      if (!selected.scope.stillCurrent()) throw new Error('Account changed before Studio project write');
      const previous = await AsyncStorage.getItem(selected.key);
      assertEpoch();
      if (!selected.scope.stillCurrent()) throw new Error('Account changed before Studio project publication');
      if (key === KEYS.projects && observedProjects !== undefined && previous !== observedProjects) {
        throw new Error('Studio project library changed; reload before saving');
      }
      await AsyncStorage.setItem(selected.key, value);
      if (getAuthEpoch() !== expectedEpoch || !selected.scope.stillCurrent()) {
        // Only undo the exact stale write. Another process is not covered
        // by the JS queue; do not blindly overwrite a changed disk value.
        if (await AsyncStorage.getItem(selected.key) === value && previous !== value) {
          if (previous === null) await AsyncStorage.removeItem(selected.key);
          else await AsyncStorage.setItem(selected.key, previous);
        }
        throw new Error('Account changed during Studio project write');
      }
      if (key === KEYS.projects) observedProjects = value;
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

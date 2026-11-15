/** Explicit, account-scoped preset storage. Never reads the old unscoped key. */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { getAuthEpoch } from '../auth/gameforgeAuth';
import { creatorStorageScope } from './creatorStorageScope';
import { DESIGN_PRESET_STORAGE_KEY, decodeDesignPresets, encodeDesignPresets, type DesignPreset } from './designPresets';

export interface DesignPresetLease {
  stillCurrent(): boolean;
  read(): Promise<DesignPreset[]>;
  update(operation: (items: readonly DesignPreset[]) => DesignPreset[]): Promise<DesignPreset[]>;
}

const tails = new Map<string, Promise<void>>();
async function serial<T>(key: string, operation: () => Promise<T>): Promise<T> {
  const prior = tails.get(key) ?? Promise.resolve();
  let done!: () => void;
  const next = new Promise<void>(resolve => { done = resolve; });
  const tail = prior.then(() => next);
  tails.set(key, tail);
  await prior;
  try { return await operation(); }
  finally { done(); if (tails.get(key) === tail) tails.delete(key); }
}

export async function openDesignPresetLease(expectedEpoch: number): Promise<DesignPresetLease> {
  if (getAuthEpoch() !== expectedEpoch) throw new Error('Stale design editor');
  const scope = await creatorStorageScope(DESIGN_PRESET_STORAGE_KEY);
  const stillCurrent = () => scope.stillCurrent() && getAuthEpoch() === expectedEpoch;
  const assertOwner = () => { if (!stillCurrent()) throw new Error('Design preset account changed'); };
  assertOwner();
  const readOwned = async (): Promise<DesignPreset[]> => {
    assertOwner();
    const raw = await AsyncStorage.getItem(scope.key);
    assertOwner();
    // A damaged library is held; never substitute [] and overwrite it.
    return decodeDesignPresets(raw);
  };
  return {
    stillCurrent,
    read: () => serial(scope.key, readOwned),
    update: operation => serial(scope.key, async () => {
      assertOwner();
      const previous = await AsyncStorage.getItem(scope.key);
      assertOwner();
      const current = decodeDesignPresets(previous);
      const next = operation(current);
      const encoded = encodeDesignPresets(next);
      assertOwner();
      await AsyncStorage.setItem(scope.key, encoded);
      if (!stillCurrent()) {
        if (await AsyncStorage.getItem(scope.key) === encoded && previous !== encoded) {
          if (previous === null) await AsyncStorage.removeItem(scope.key);
          else await AsyncStorage.setItem(scope.key, previous);
        }
        assertOwner();
      }
      return decodeDesignPresets(encoded);
    }),
  };
}

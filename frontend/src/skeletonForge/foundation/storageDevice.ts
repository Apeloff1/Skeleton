/**
 * AsyncStorage adapter for the studio shell. Imported only by the live screen.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import type { Kv } from './storage';

export function asyncStorageKv(): Kv {
  return {
    getItem: (key) => AsyncStorage.getItem(key),
    setItem: (key, value) => AsyncStorage.setItem(key, value),
  };
}

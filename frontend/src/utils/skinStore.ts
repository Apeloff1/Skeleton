/**
 * Runtime skin store.
 *
 * The default skin is applied synchronously so first paint already uses the
 * canonical palette. Async hydration only notifies React when the persisted
 * skin is actually different, avoiding a redundant root remount + storage
 * write on the common/default startup path.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useSyncExternalStore } from 'react';
import theme from '../../theme/tokens';
import { SKIN_BY_ID, DEFAULT_SKIN, type Skin } from '../../theme/skins';

const KEY = 'app_skin_v1';
const BASE = { ...(theme as any).colors };

let activeId = DEFAULT_SKIN;
let version = 0;
const listeners = new Set<() => void>();

function emit() {
  version += 1;
  listeners.forEach(listener => listener());
}

function applyPalette(id: string): boolean {
  const skin: Skin | undefined = SKIN_BY_ID[id];
  if (!skin) return false;
  activeId = id;
  Object.assign((theme as any).colors, BASE, skin.colors);
  return true;
}

// First render should already match the documented default skin. Do this
// without emitting or persisting: there are no subscribers yet, and writing
// the same default value on every app launch only adds storage I/O.
applyPalette(DEFAULT_SKIN);

export function applySkin(id: string) {
  const skin: Skin | undefined = SKIN_BY_ID[id];
  if (!skin) return;

  const changed = activeId !== id;
  if (changed) {
    applyPalette(id);
    emit();
  }

  // Explicit user selection is the only path that persists a value.
  AsyncStorage.setItem(KEY, id).catch(() => {});
}

export async function initSkin() {
  try {
    const saved = await AsyncStorage.getItem(KEY);
    const next = saved && SKIN_BY_ID[saved] ? saved : DEFAULT_SKIN;
    if (next === activeId) return;
    if (applyPalette(next)) emit();
  } catch {
    // The default palette is already synchronously applied. Storage failure
    // therefore requires no write, re-application, or subscriber notification.
  }
}

export function getActiveSkinId() {
  return activeId;
}

export function useActiveSkin() {
  const v = useSyncExternalStore(
    callback => {
      listeners.add(callback);
      return () => listeners.delete(callback);
    },
    () => version,
    () => version,
  );
  return { id: activeId, version: v };
}

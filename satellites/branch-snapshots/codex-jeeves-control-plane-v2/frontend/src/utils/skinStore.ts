/**
 * 🎨 SKIN STORE — applies one of 30 app skins to the LIVE palette (theme.colors) at runtime,
 * persists the choice, and notifies subscribers so the root layout can remount + re-tint.
 * Default skin: "hyperwave".
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useSyncExternalStore } from 'react';
import theme from '../../theme/tokens';
import { SKIN_BY_ID, DEFAULT_SKIN, type Skin } from '../../theme/skins';

const KEY = 'app_skin_v1';

// Snapshot the original palette ONCE so we can always rebuild from a clean base.
const BASE = { ...(theme as any).colors };

let activeId = DEFAULT_SKIN;
let version = 0;
const listeners = new Set<() => void>();

function emit() {
  version += 1;
  listeners.forEach((l) => l());
}

export function applySkin(id: string) {
  const skin: Skin | undefined = SKIN_BY_ID[id];
  if (!skin) return;
  activeId = id;
  // Rebuild from base, then overlay this skin's keys — keeps reskins clean + reversible.
  Object.assign((theme as any).colors, BASE, skin.colors);
  emit();
  AsyncStorage.setItem(KEY, id).catch(() => {});
}

export async function initSkin() {
  try {
    const saved = (await AsyncStorage.getItem(KEY)) || DEFAULT_SKIN;
    applySkin(SKIN_BY_ID[saved] ? saved : DEFAULT_SKIN);
  } catch {
    applySkin(DEFAULT_SKIN);
  }
}

export function getActiveSkinId() {
  return activeId;
}

// React hook — re-renders consumers when the skin changes.
export function useActiveSkin() {
  const v = useSyncExternalStore(
    (cb) => { listeners.add(cb); return () => listeners.delete(cb); },
    () => version,
    () => version,
  );
  return { id: activeId, version: v };
}

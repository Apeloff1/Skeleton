/**
 * menuPrefs — persistent pinned + hidden feature ids for /menu.
 *
 *   • Stored at `@codedock/menu:prefs`
 *   • Hook re-emits on subscribe so multiple consumers stay in sync
 *   • Pin reorders the card to the top of its category
 *   • Hide removes the card from the catalog (recoverable from
 *     `/settings/feature-flags` later, or by clearing prefs)
 */
import { useEffect, useState } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';

const KEY = '@codedock/menu:prefs';

export interface MenuPrefs {
  pinned: string[];   // feature ids
  hidden: string[];   // feature ids
}

const DEFAULTS: MenuPrefs = { pinned: [], hidden: [] };
let _cache: MenuPrefs = DEFAULTS;
const listeners = new Set<(p: MenuPrefs) => void>();

let _hydrated = false;
async function _hydrate() {
  if (_hydrated) return;
  _hydrated = true;
  try {
    const raw = await AsyncStorage.getItem(KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      _cache = {
        pinned: Array.isArray(parsed?.pinned) ? parsed.pinned : [],
        hidden: Array.isArray(parsed?.hidden) ? parsed.hidden : [],
      };
      emit();
    }
  } catch { /* swallow */ }
}

function emit() { for (const l of listeners) try { l(_cache); } catch {} }

async function save() {
  try { await AsyncStorage.setItem(KEY, JSON.stringify(_cache)); } catch { /* swallow */ }
}

export function getMenuPrefs(): MenuPrefs { return _cache; }
export function isPinned(id: string): boolean { return _cache.pinned.includes(id); }
export function isHidden(id: string): boolean { return _cache.hidden.includes(id); }

export async function togglePin(id: string): Promise<boolean> {
  const has = _cache.pinned.includes(id);
  _cache = {
    ...(_cache),
    pinned: has ? _cache.pinned.filter(x => x !== id) : [..._cache.pinned, id],
  };
  emit(); await save();
  return !has;
}

export async function toggleHide(id: string): Promise<boolean> {
  const has = _cache.hidden.includes(id);
  _cache = {
    ...(_cache),
    hidden: has ? _cache.hidden.filter(x => x !== id) : [..._cache.hidden, id],
    // If hiding a pinned card, also unpin to avoid orphan state
    pinned: has ? _cache.pinned : _cache.pinned.filter(x => x !== id),
  };
  emit(); await save();
  return !has;
}

export async function resetMenuPrefs(): Promise<void> {
  _cache = { pinned: [], hidden: [] };
  emit(); await save();
}

/** React hook → returns latest prefs and triggers re-render on changes. */
export function useMenuPrefs(): MenuPrefs {
  const [p, setP] = useState<MenuPrefs>(_cache);
  useEffect(() => {
    _hydrate().then(() => setP(_cache));
    const l = (np: MenuPrefs) => setP(np);
    listeners.add(l);
    return () => { listeners.delete(l); };
  }, []);
  return p;
}

export default { getMenuPrefs, useMenuPrefs, togglePin, toggleHide, isPinned, isHidden, resetMenuPrefs };

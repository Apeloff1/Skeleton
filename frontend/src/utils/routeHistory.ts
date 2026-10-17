/**
 * routeHistory.ts — Per-route AsyncStorage helper for "Recent runs" strips.
 *
 * Each of the power-feature routes (/debugger, /intelligence, /agents,
 * /imagine, /assets, /music, /rosetta, /playground, /collab) can use
 * `useRouteHistory(key)` to remember the last 20 runs and surface them as
 * tappable cards or chips. The shape is intentionally loose — each route
 * stores whatever blob it wants in `payload`.
 */
import { useEffect, useState, useCallback } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';

export interface HistoryEntry<T = any> {
  id: string;
  ts: number;
  label: string;     // short display title
  preview?: string;  // 1-2 line snippet
  payload: T;        // route-specific data to re-load
}

export function useRouteHistory<T = any>(key: string, max = 20) {
  const storageKey = `@codedock:hist:${key}:v1`;
  const [items, setItems] = useState<HistoryEntry<T>[]>([]);

  useEffect(() => {
    (async () => {
      try {
        const raw = await AsyncStorage.getItem(storageKey);
        if (raw) setItems(JSON.parse(raw));
      } catch {}
    })();
  }, [storageKey]);

  const push = useCallback(async (entry: Omit<HistoryEntry<T>, 'id' | 'ts'>) => {
    const next: HistoryEntry<T> = {
      ...entry,
      id: `h_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 6)}`,
      ts: Date.now(),
    };
    const newList = [next, ...items].slice(0, max);
    setItems(newList);
    try { await AsyncStorage.setItem(storageKey, JSON.stringify(newList)); } catch {}
    return next;
  }, [items, storageKey, max]);

  const clear = useCallback(async () => {
    setItems([]);
    try { await AsyncStorage.removeItem(storageKey); } catch {}
  }, [storageKey]);

  const remove = useCallback(async (id: string) => {
    const next = items.filter(i => i.id !== id);
    setItems(next);
    try { await AsyncStorage.setItem(storageKey, JSON.stringify(next)); } catch {}
  }, [items, storageKey]);

  return { items, push, clear, remove };
}

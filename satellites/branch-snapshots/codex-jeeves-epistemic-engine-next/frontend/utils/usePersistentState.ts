/**
 * usePersistentState — useState replacement with transparent AsyncStorage
 * persistence. Identical API to useState, plus an optional version key
 * for safe schema migrations.
 *
 *   const [count, setCount] = usePersistentState('counter', 0);
 *
 * Differences from useAutosave:
 *   • usePersistentState always serialises the WHOLE value on every change
 *     (debounced).
 *   • Returns the regular `[value, setValue]` tuple — no extra control object.
 *   • Supports a `version` parameter that wipes old state when bumped (use
 *     for breaking schema changes).
 *
 * Use this for any module-local state that should survive backgrounding,
 * crashes, or app updates (e.g. last selected tab, accordion expansion
 * state, sort order, theme preferences).
 */
import { useEffect, useRef, useState } from 'react';
import { safeGetItem, safeSetItem } from './safeStorage';
import { safeJsonParse, safeJsonStringify } from './safeJson';

const PREFIX = '@persist/';

export function usePersistentState<T>(
  key: string,
  initial: T,
  opts: { debounceMs?: number; version?: number } = {},
): [T, React.Dispatch<React.SetStateAction<T>>] {
  const storageKey  = `${PREFIX}${opts.version ?? 1}/${key}`;
  const debounceMs  = opts.debounceMs ?? 300;
  const [value, setValue] = useState<T>(initial);
  const ready = useRef(false);
  const saveT = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Restore on mount.
  useEffect(() => {
    (async () => {
      try {
        const raw = await safeGetItem(storageKey, null, 600);
        if (raw != null) setValue(safeJsonParse<T>(raw, initial));
      } finally { ready.current = true; }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storageKey]);

  useEffect(() => {
    if (!ready.current) return;
    if (saveT.current) clearTimeout(saveT.current);
    saveT.current = setTimeout(() => {
      safeSetItem(storageKey, safeJsonStringify(value), 800).catch(() => {});
    }, debounceMs);
    return () => { if (saveT.current) clearTimeout(saveT.current); };
  }, [value, storageKey, debounceMs]);

  return [value, setValue];
}

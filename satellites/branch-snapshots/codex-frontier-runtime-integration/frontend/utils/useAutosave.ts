/**
 * useAutosave — auto-persist a piece of state to AsyncStorage.
 *
 *   const [draft, setDraft] = useAutosave<Draft>('compose-draft', { title: '' });
 *
 *   On every change, the value is debounced + serialised + saved with
 *   safeStorage. On mount, the previously-saved value is restored.
 *
 *   useful for:
 *     • Long-form input that survives accidental backgrounding
 *     • Multi-step form state
 *     • Cached query parameters across sessions
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { safeGetItem, safeSetItem } from './safeStorage';
import { safeJsonParse, safeJsonStringify } from './safeJson';

const PREFIX = '@autosave/';

export function useAutosave<T>(
  key: string,
  initial: T,
  options: { debounceMs?: number; storageKey?: string } = {},
): [T, (next: T) => void, { reset: () => void; ready: boolean }] {
  const debounceMs = options.debounceMs ?? 350;
  const storageKey = options.storageKey ?? (PREFIX + key);
  const [value, setValue] = useState<T>(initial);
  const [ready, setReady] = useState(false);
  const lastSaveT = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mounted = useRef(true);

  // Restore on mount.
  useEffect(() => {
    (async () => {
      try {
        const raw = await safeGetItem(storageKey, null, 600);
        if (raw != null && mounted.current) {
          const parsed = safeJsonParse<T>(raw, initial);
          setValue(parsed);
        }
      } finally {
        if (mounted.current) setReady(true);
      }
    })();
    return () => { mounted.current = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storageKey]);

  // Debounced save on every change.
  useEffect(() => {
    if (!ready) return;
    if (lastSaveT.current) clearTimeout(lastSaveT.current);
    lastSaveT.current = setTimeout(() => {
      safeSetItem(storageKey, safeJsonStringify(value), 800).catch(() => {});
    }, debounceMs);
    return () => { if (lastSaveT.current) clearTimeout(lastSaveT.current); };
  }, [value, ready, storageKey, debounceMs]);

  const reset = useCallback(() => {
    setValue(initial);
    safeSetItem(storageKey, safeJsonStringify(initial), 800).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storageKey]);

  return [value, setValue, { reset, ready }];
}

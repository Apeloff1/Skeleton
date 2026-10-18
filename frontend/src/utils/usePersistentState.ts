/**
 * Key-scoped, hydration-safe persisted state for UI preferences and layout.
 *
 * A user edit made before an AsyncStorage read resolves wins over that read.
 * Writes are serialized per key even across remounts; a slow old save can
 * never overwrite a newer write. Unmount flushes unsaved debounced edits.
 * This is not a transactional replacement for the canonical studio database.
 */
import { useEffect, useRef, useState } from 'react';
import { safeGetItem, safeSetItem } from './safeStorage';
import { safeJsonParse } from './safeJson';

const PREFIX = '@persist/';
const MAX_PERSIST_CHARS = 1024 * 1024;
const writeTails = new Map<string, Promise<void>>();

function serialize<T>(value: T): string | null {
  try {
    const payload = JSON.stringify(value);
    if (typeof payload !== 'string' || payload.length > MAX_PERSIST_CHARS) return null;
    return payload;
  } catch { return null; }
}

/**
 * Write-fence promises retain ordering across independent hook instances,
 * unmounts and re-mounts. The tail map only retains active keys.
 */
export function queuePersistentStateWrite(key: string, raw: string): Promise<boolean> {
  if (!key.startsWith(PREFIX) || raw.length > MAX_PERSIST_CHARS) return Promise.resolve(false);
  const predecessor = writeTails.get(key) ?? Promise.resolve();
  const write = predecessor.then(() => safeSetItem(key, raw, 2_000));
  const settled = write.then(() => undefined, () => undefined);
  writeTails.set(key, settled);
  void settled.then(() => {
    if (writeTails.get(key) === settled) writeTails.delete(key);
  });
  return write.catch(() => false);
}
export function pendingPersistentStateKeys(): number { return writeTails.size; }

interface LocalState<T> {
  key: string;
  value: T;
  revision: number;
  writtenRevision: number;
  loaded: boolean;
  timer: ReturnType<typeof setTimeout> | null;
}

export function usePersistentState<T>(
  key: string,
  initial: T,
  opts: { debounceMs?: number; version?: number } = {},
): [T, React.Dispatch<React.SetStateAction<T>>] {
  const storageKey = `${PREFIX}${opts.version ?? 1}/${key}`;
  const debounceMs = Number.isFinite(opts.debounceMs)
    ? Math.max(0, Math.min(60_000, opts.debounceMs!)) : 300;
  const [value, setValue] = useState<T>(initial);
  const mountedRef = useRef(true);
  const epochRef = useRef(0);
  const localRef = useRef<LocalState<T>>({
    key: storageKey, value: initial, revision: 0,
    writtenRevision: 0, loaded: false, timer: null,
  });

  const persist = (snapshot: LocalState<T>) => {
    if (snapshot.revision <= snapshot.writtenRevision) return;
    const raw = serialize(snapshot.value);
    if (raw === null) return;
    const revision = snapshot.revision;
    void queuePersistentStateWrite(snapshot.key, raw).then(ok => {
      if (ok) snapshot.writtenRevision = Math.max(snapshot.writtenRevision, revision);
    });
  };
  const schedule = (state: LocalState<T>) => {
    if (state.timer) clearTimeout(state.timer);
    if (!state.loaded || state.revision <= state.writtenRevision) return;
    state.timer = setTimeout(() => {
      state.timer = null;
      persist(state);
    }, debounceMs);
  };

  useEffect(() => {
    mountedRef.current = true;
    const epoch = ++epochRef.current;
    const state: LocalState<T> = {
      key: storageKey, value: initial, revision: 0,
      writtenRevision: 0, loaded: false, timer: null,
    };
    localRef.current = state;
    setValue(initial);
    void (async () => {
      const raw = await safeGetItem(storageKey, null, 600);
      if (!mountedRef.current || epoch !== epochRef.current) return;
      if (state.revision === 0 && raw !== null) {
        const restored = safeJsonParse<T>(raw, initial);
        state.value = restored;
        setValue(restored);
      }
      state.loaded = true;
      if (state.revision > 0) schedule(state);
    })().catch(() => {
      if (mountedRef.current && epoch === epochRef.current) {
        state.loaded = true;
        if (state.revision > 0) schedule(state);
      }
    });
    return () => {
      // The setup epoch is the authority being invalidated. Assign it
      // directly so cleanup never reads a potentially changed ref value.
      epochRef.current = epoch + 1;
      if (state.timer) clearTimeout(state.timer);
      state.timer = null;
      persist(state); // no state update, best effort but ordered native write
      mountedRef.current = false;
    };
    // Changing key/version intentionally starts a new persistence authority.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storageKey]);

  const setPersistent: React.Dispatch<React.SetStateAction<T>> = next => {
    if (!mountedRef.current) return;
    const state = localRef.current;
    // Use the current authoritative snapshot, not a potentially stale React
    // render closure. Concurrent functional edits therefore compose.
    const updated = typeof next === 'function'
      ? (next as (current: T) => T)(state.value) : next;
    state.value = updated;
    state.revision++;
    setValue(updated);
    if (state.loaded) schedule(state);
  };
  return [value, setPersistent];
}

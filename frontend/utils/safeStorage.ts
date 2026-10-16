/**
 * safeStorage — defensive wrapper around AsyncStorage.
 *
 * Why this exists:
 *   On heavily-modded Android (esp. Samsung OneUI with user-encrypted
 *   storage profiles), AsyncStorage can occasionally hang for tens of
 *   seconds before user unlocks the device. If the app awaits one of
 *   those calls during boot, it freezes BEFORE any UI renders and
 *   Android kills the process. We wrap every call in:
 *
 *     • A hard timeout (default 800ms — generous for normal flash I/O,
 *       short enough that the boot UI always paints first).
 *     • A try/catch that returns a sane default rather than throwing.
 *     • Optional in-memory mirror so repeated reads after a successful
 *       first hit don't pay the I/O cost again.
 *
 * Usage:
 *   const seen = await safeGetItem('@codedock:welcome_seen:v1', null, 500);
 *   await safeSetItem('@codedock:welcome_seen:v1', '1');
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

const _mirror = new Map<string, string | null>();

// ─────────────────────────────────────────────────────────────────────
// Stale-key self-pruning (added 2026-02).
// Sidecar metadata records the write-timestamp of every key managed by
// safeSetItem so pruneExpired() can drop entries older than a TTL. We
// keep it in a SINGLE JSON blob to avoid N round-trips and to keep the
// pruner O(1) on cold boots (one read + at most one write).
// ─────────────────────────────────────────────────────────────────────
const META_KEY = '@safeStorage:meta:v1';
const DEFAULT_PRUNE_PREFIXES = [
  '@boot/',
  '@codedock/',
  // ★ Feb 2026: also prune feature-flag + telemetry caches so they age out
  // naturally instead of growing forever on the dev box.
  '@feature-flags/',
  '@telemetry/',
];
const DEFAULT_TTL_MS = 7 * 24 * 60 * 60 * 1000; // 7 days
// Crash-loop and archived evidence are operator recovery state, not cache.
const RECOVERY_EVIDENCE_KEYS = new Set([
  '@boot/crash_count', '@boot/last_clean_boot', '@boot/trace', '@boot/sessions',
]);

let _metaCache: Record<string, number> | null = null;
let _metaDirty = false;

async function _loadMeta(): Promise<Record<string, number>> {
  if (_metaCache) return _metaCache;
  try {
    const raw = await timeout(AsyncStorage.getItem(META_KEY), 800, null);
    _metaCache = raw ? JSON.parse(raw) : {};
  } catch {
    _metaCache = {};
  }
  return _metaCache!;
}

async function _flushMeta() {
  if (!_metaDirty || !_metaCache) return;
  _metaDirty = false;
  try {
    const ok = await timeout(AsyncStorage.setItem(META_KEY, JSON.stringify(_metaCache)).then(() => true), 800, false);
    if (!ok) _metaDirty = true; // a failed metadata flush must remain retryable
  } catch {
    _metaDirty = true;
  }
}

function _shouldTrack(key: string, prefixes: string[]): boolean {
  return !RECOVERY_EVIDENCE_KEYS.has(key) && prefixes.some(p => key.startsWith(p));
}

function timeout<T>(p: Promise<T>, ms: number, fallback: T): Promise<T> {
  return new Promise<T>((resolve) => {
    let done = false;
    const t = setTimeout(() => {
      if (!done) { done = true; resolve(fallback); }
    }, ms);
    p.then(v => {
      if (!done) { done = true; clearTimeout(t); resolve(v); }
    }).catch(() => {
      if (!done) { done = true; clearTimeout(t); resolve(fallback); }
    });
  });
}

export async function safeGetItem(key: string, fallback: string | null = null, ms = 800): Promise<string | null> {
  if (_mirror.has(key)) return _mirror.get(key) ?? fallback;
  try {
    const result = await timeout(
      AsyncStorage.getItem(key).then(value => ({ ok: true, value })),
      ms,
      { ok: false, value: fallback },
    );
    // Do not permanently cache a timeout as a real stored value.
    if (!result.ok) return fallback;
    _mirror.set(key, result.value);
    return result.value;
  } catch { return fallback; }
}

export async function safeSetItem(key: string, value: string, ms = 800): Promise<boolean> {
  _mirror.set(key, value); // optimistic mirror — read-after-write is always consistent
  try {
    const saved = await timeout(AsyncStorage.setItem(key, value).then(() => true), ms, false);
    if (!saved) {
      // A timed-out write is unverified: invalidate the optimistic mirror.
      if (_mirror.get(key) === value) _mirror.delete(key);
      return false;
    }
    // Update sidecar metadata for prune-eligible keys.
    if (_shouldTrack(key, DEFAULT_PRUNE_PREFIXES)) {
      const meta = await _loadMeta();
      meta[key] = Date.now();
      _metaDirty = true;
      // Flush lazily — don't await (best-effort, the next prune flushes too).
      void _flushMeta();
    }
    return true;
  } catch {
    if (_mirror.get(key) === value) _mirror.delete(key);
    return false;
  }
}

export async function safeRemoveItem(key: string, ms = 800): Promise<boolean> {
  _mirror.delete(key);
  try {
    const removed = await timeout(AsyncStorage.removeItem(key).then(() => true), ms, false);
    if (!removed) return false;
    if (_metaCache && key in _metaCache) {
      delete _metaCache[key];
      _metaDirty = true;
      void _flushMeta();
    }
    return true;
  } catch { return false; }
}

export async function safeMultiRemove(keys: string[], ms = 1500): Promise<boolean> {
  for (const k of keys) _mirror.delete(k);
  try {
    const removed = await timeout(AsyncStorage.multiRemove(keys).then(() => true), ms, false);
    if (!removed) return false;
    if (_metaCache) {
      let touched = false;
      for (const k of keys) {
        if (k in _metaCache) { delete _metaCache[k]; touched = true; }
      }
      if (touched) { _metaDirty = true; void _flushMeta(); }
    }
    return true;
  } catch { return false; }
}

export function clearMirror() { _mirror.clear(); _metaCache = null; }

// ─────────────────────────────────────────────────────────────────────
// pruneExpired — drop @boot/* and @codedock/* entries older than `ttlMs`.
// Safe to call on every cold boot; ~O(meta-size) memory, single multiRemove.
// Returns the number of keys actually purged.
// ─────────────────────────────────────────────────────────────────────
export interface PruneResult {
  scanned: number;
  pruned: number;
  prunedKeys: string[];
  elapsedMs: number;
}

export async function pruneExpired(opts: {
  ttlMs?: number;
  prefixes?: string[];
  scanAllKeys?: boolean;  // also scan AsyncStorage.getAllKeys() and prune untracked stale keys
  ms?: number;
} = {}): Promise<PruneResult> {
  const started = Date.now();
  const ttl = opts.ttlMs ?? DEFAULT_TTL_MS;
  const prefixes = opts.prefixes ?? DEFAULT_PRUNE_PREFIXES;
  const scanAll = opts.scanAllKeys ?? true;
  const timeoutMs = opts.ms ?? 1500;

  const meta = await _loadMeta();
  const now = Date.now();
  const expired = new Set<string>();
  let scanned = 0;

  // 1. Walk tracked meta entries.
  for (const [k, ts] of Object.entries(meta)) {
    scanned++;
    if (!_shouldTrack(k, prefixes)) continue;
    if (now - (ts || 0) > ttl) expired.add(k);
  }

  // 2. Sweep all keys with matching prefix; if any aren't tracked, stamp them
  //    NOW (so on the next prune they can age out). This handles legacy keys
  //    written before the meta tracking was introduced.
  if (scanAll) {
    try {
      const all: readonly string[] = await timeout(
        AsyncStorage.getAllKeys().then(v => v as readonly string[]),
        timeoutMs,
        [] as readonly string[],
      );
      for (const k of all) {
        if (!_shouldTrack(k, prefixes)) continue;
        scanned++;
        if (!(k in meta)) {
          meta[k] = now;  // first-seen — give it a fresh TTL clock.
          _metaDirty = true;
        }
      }
    } catch { /* ignore */ }
  }

  // 3. Remove expired keys + their meta entries.
  const prunedKeys = Array.from(expired);
  if (prunedKeys.length) {
    const removed = await timeout(
      AsyncStorage.multiRemove(prunedKeys).then(() => true),
      timeoutMs,
      false,
    ).catch(() => false);
    // A failed prune must not declare authoritative state deleted. Preserve
    // metadata for the next attempt; prevent a stale mirror in either case.
    for (const k of prunedKeys) _mirror.delete(k);
    if (removed) {
      for (const k of prunedKeys) delete meta[k];
      _metaDirty = true;
    } else {
      prunedKeys.length = 0;
    }
  }

  await _flushMeta();

  return {
    scanned,
    pruned: prunedKeys.length,
    prunedKeys,
    elapsedMs: Date.now() - started,
  };
}

/** Inspector helper — current sidecar metadata snapshot (used by /api/health surfaces). */
export async function _safeStorageStats(): Promise<{ tracked: number; oldestAgeMs: number | null }> {
  const meta = await _loadMeta();
  const ts = Object.values(meta);
  return {
    tracked: ts.length,
    oldestAgeMs: ts.length ? Date.now() - Math.min(...ts) : null,
  };
}

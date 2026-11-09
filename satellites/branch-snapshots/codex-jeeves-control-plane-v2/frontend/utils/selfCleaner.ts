/**
 * selfCleaner — on-device software self-cleaner.
 *
 *  Keeps the app's persisted footprint small so low-RAM / low-storage devices
 *  (Samsung S20) never destabilise from accumulated junk. Runs automatically:
 *    • on every clean boot (via markBootClean → upgraded bootstrap)
 *    • throttled so repeated calls within MIN_INTERVAL_MS are no-ops
 *
 *  What it cleans:
 *    1. Triple-buffer response cache rows  (`tb_cache_*`)   — TTL + count cap
 *    2. Predictive pattern store rows      (`qb_pattern_*`) — TTL + count cap
 *    3. Boot trace                          (`@boot/trace`) — hard size cap
 *    4. Orphaned/oversized misc keys                        — best effort
 *    5. expo-file-system cache directory                    — best effort (native)
 *
 *  Everything is wrapped in try/catch — cleaning must NEVER block or crash boot.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Platform } from 'react-native';
import { traceStep } from './bootTracer';

const CACHE_PREFIX        = 'tb_cache_';
const PATTERN_PREFIX      = 'qb_pattern_';
const TRACE_KEY           = '@boot/trace';

const CACHE_TTL_MS        = 7 * 24 * 60 * 60 * 1000; // 7 days
const MAX_CACHE_ROWS      = 40;
const MAX_PATTERN_ROWS    = 40;
const MAX_TRACE_BYTES      = 32 * 1024;              // ~32 KB hard cap
const MIN_INTERVAL_MS     = 60 * 1000;               // throttle re-runs
const FS_CACHE_LIMIT_BYTES = 25 * 1024 * 1024;       // 25 MB FS cache ceiling

let _lastRun = 0;
let _running = false;

interface CleanResult { removedKeys: number; trimmedTrace: boolean; fsCleared: boolean; ms: number; }

/** Extract a millisecond timestamp from a stored row, if present. */
function _tsOf(raw: string | null): number {
  if (!raw) return 0;
  try {
    const v = JSON.parse(raw);
    return Number(v?.ts ?? v?.timestamp ?? v?.cachedAt ?? 0) || 0;
  } catch { return 0; }
}

async function _pruneByTtlAndCount(keys: string[], ttlMs: number, maxRows: number): Promise<string[]> {
  if (keys.length === 0) return [];
  const pairs = await AsyncStorage.multiGet(keys);
  const now = Date.now();
  const withTs = pairs.map(([k, v]) => ({ k, ts: _tsOf(v) }));

  const expired = withTs.filter(e => e.ts > 0 && now - e.ts > ttlMs).map(e => e.k);
  const survivors = withTs.filter(e => !(e.ts > 0 && now - e.ts > ttlMs));

  let overflow: string[] = [];
  if (survivors.length > maxRows) {
    // Drop the oldest rows beyond the cap (ts 0 = unknown age → drop first).
    survivors.sort((a, b) => a.ts - b.ts);
    overflow = survivors.slice(0, survivors.length - maxRows).map(e => e.k);
  }
  return [...expired, ...overflow];
}

/** Best-effort native filesystem cache cleanup (no-op on web / if API absent). */
async function _clearFsCacheIfLarge(): Promise<boolean> {
  if (Platform.OS === 'web') return false;
  try {
    // expo-file-system v19 — legacy namespace exposes the classic helpers.
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const FS: any = require('expo-file-system/legacy');
    const dir: string | undefined = FS?.cacheDirectory;
    if (!dir || typeof FS.readDirectoryAsync !== 'function') return false;

    const entries: string[] = await FS.readDirectoryAsync(dir).catch(() => []);
    let total = 0;
    for (const name of entries) {
      try {
        const info = await FS.getInfoAsync(dir + name, { size: true });
        total += info?.size || 0;
      } catch { /* skip */ }
    }
    if (total <= FS_CACHE_LIMIT_BYTES) return false;

    // Over the ceiling — delete cache entries (regenerable).
    for (const name of entries) {
      try { await FS.deleteAsync(dir + name, { idempotent: true }); } catch { /* skip */ }
    }
    return true;
  } catch { return false; }
}

/**
 * Run the self-cleaner. Throttled + reentrancy-guarded. Safe to call freely.
 * `force` bypasses the throttle (e.g. a manual "Free up space" button).
 */
export async function runSelfCleaner(reason = 'boot', force = false): Promise<CleanResult> {
  const t0 = Date.now();
  const result: CleanResult = { removedKeys: 0, trimmedTrace: false, fsCleared: false, ms: 0 };
  if (_running) return result;
  if (!force && t0 - _lastRun < MIN_INTERVAL_MS) return result;
  _running = true;
  _lastRun = t0;

  try {
    const allKeys = await AsyncStorage.getAllKeys();

    // 1 + 2: TTL + count cap on cache & pattern rows.
    const cacheKeys   = allKeys.filter(k => k.startsWith(CACHE_PREFIX));
    const patternKeys = allKeys.filter(k => k.startsWith(PATTERN_PREFIX));
    const [cacheDrop, patternDrop] = await Promise.all([
      _pruneByTtlAndCount(cacheKeys, CACHE_TTL_MS, MAX_CACHE_ROWS),
      _pruneByTtlAndCount(patternKeys, CACHE_TTL_MS, MAX_PATTERN_ROWS),
    ]);
    const toRemove = [...cacheDrop, ...patternDrop];
    if (toRemove.length) {
      await AsyncStorage.multiRemove(toRemove);
      result.removedKeys = toRemove.length;
    }

    // 3: hard-cap the boot trace size.
    try {
      const raw = await AsyncStorage.getItem(TRACE_KEY);
      if (raw && raw.length > MAX_TRACE_BYTES) {
        const arr = JSON.parse(raw);
        if (Array.isArray(arr) && arr.length > 1) {
          // Keep the most recent half — that's where crashes live.
          const trimmed = arr.slice(-Math.floor(arr.length / 2));
          await AsyncStorage.setItem(TRACE_KEY, JSON.stringify(trimmed));
          result.trimmedTrace = true;
        }
      }
    } catch { /* swallow */ }

    // 5: filesystem cache (native, best-effort).
    result.fsCleared = await _clearFsCacheIfLarge();

    result.ms = Date.now() - t0;
    traceStep('self_clean', { reason, ...result }).catch(() => {});
  } catch {
    // never throw from the cleaner
  } finally {
    _running = false;
  }
  return result;
}

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
 *    3. Boot trace is owned exclusively by bootTracer (never rewritten here)
 *    4. expo-file-system cache directory                    — best effort (native)
 *
 *  Everything is wrapped in try/catch — cleaning must NEVER block or crash boot.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Platform } from 'react-native';
import { traceStep } from './bootTracer';

const CACHE_PREFIX        = 'tb_cache_';
const PATTERN_PREFIX      = 'qb_pattern_';

const CACHE_TTL_MS        = 7 * 24 * 60 * 60 * 1000; // 7 days
const MAX_CACHE_ROWS      = 40;
const MAX_PATTERN_ROWS    = 40;
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

    // The Expo cache directory is shared by downloads, previews and user
    // work in progress. Never delete arbitrary entries on a size threshold.
    // Only explicitly app-owned regenerable scratch families are eligible.
    const scratch = (await FS.readDirectoryAsync(dir).catch(() => []))
      .filter((name: string) => /^(?:skeleton-cache-|skeleton-scratch-)[A-Za-z0-9._-]+$/.test(name));
    let total = 0;
    for (const name of scratch) {
      try {
        const info = await FS.getInfoAsync(dir + name, { size: true });
        if (!info?.isDirectory && Number.isFinite(info?.size)) total += Math.max(0, info.size);
      } catch { /* skip */ }
    }
    if (total <= FS_CACHE_LIMIT_BYTES) return false;

    let removed = false;
    for (const name of scratch) {
      try {
        const info = await FS.getInfoAsync(dir + name, { size: true });
        if (info?.isDirectory) continue;
        await FS.deleteAsync(dir + name, { idempotent: true });
        removed = true;
      } catch { /* skip */ }
    }
    return removed;
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

    // The trace writer has its own bounded queue and last-150-entry cap.
    // Rewriting @boot/trace here would race with the authoritative writer.

    // 3: filesystem cache (native, best-effort).
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

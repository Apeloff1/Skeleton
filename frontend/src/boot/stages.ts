/**
 * src/boot/stages.ts — declarative frontend boot stages.
 *
 * Phase 0 is intentionally LOCAL-ONLY: it must be able to reach an
 * interactive screen without waiting on a server, tunnel, or scale-to-zero
 * backend. Network work lives in phase 1 and housekeeping in phase 2.
 */
import { Platform } from 'react-native';
import { safeGetItem, safeSetItem, pruneExpired } from '../../utils/safeStorage';
import api from '../utils/apiClient';
import { probeBackend } from '../utils/bootHealth';

export interface StageRun { ok: boolean; note?: string }
export interface BootStageDef {
  id: string;
  label: string;
  deps: string[];
  timeoutMs: number;
  critical: boolean;
  weight: number;
  phase: 0 | 1 | 2;
  retries?: number;
  backoffMs?: number;
  run: (signal?: AbortSignal) => Promise<StageRun>;
}

const BOOT_CACHE_KEY = '@boot/last_ok:v1';

export interface CachedBoot {
  ts: number;
  score: number;
  backendOk: boolean;
}

export async function readBootCache(): Promise<CachedBoot | null> {
  try {
    const raw = await safeGetItem(BOOT_CACHE_KEY, null, 500);
    if (!raw) return null;
    const c = JSON.parse(raw as string);
    return c && typeof c === 'object' ? c as CachedBoot : null;
  } catch { return null; }
}

export async function writeBootCache(snap: CachedBoot): Promise<void> {
  try { await safeSetItem(BOOT_CACHE_KEY, JSON.stringify(snap)); } catch { /* swallow */ }
}

function _sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new Error('aborted'));
      return;
    }

    let settled = false;
    const finish = (fn: () => void) => {
      if (settled) return;
      settled = true;
      signal?.removeEventListener?.('abort', onAbort);
      fn();
    };
    const timer = setTimeout(() => finish(resolve), ms);
    const onAbort = () => {
      clearTimeout(timer);
      finish(() => reject(new Error('aborted')));
    };
    signal?.addEventListener?.('abort', onAbort, { once: true } as any);
  });
}

export const STAGES: BootStageDef[] = [
  {
    id: 'storage', label: 'Local storage', deps: [],
    timeoutMs: 900, critical: true, weight: 20, phase: 0,
    retries: 1, backoffMs: 200,
    run: async (signal) => {
      if (signal?.aborted) return { ok: false, note: 'aborted' };
      const k = `__boot_probe_${Date.now() % 1e6}`;
      await safeSetItem(k, '1', 600);
      const v = await safeGetItem(k, null, 600);
      return v === '1' ? { ok: true } : { ok: false, note: 'read-back failed' };
    },
  },
  {
    id: 'finalize', label: 'Finalizing', deps: ['storage'],
    timeoutMs: 200, critical: false, weight: 10, phase: 0,
    run: async (signal) => {
      try { await _sleep(60, signal); } catch { return { ok: false, note: 'aborted' }; }
      return { ok: true };
    },
  },
  {
    id: 'crash_guard', label: 'Crash-loop guard', deps: ['storage'],
    timeoutMs: 700, critical: false, weight: 10, phase: 1,
    run: async (signal) => {
      if (signal?.aborted) return { ok: false, note: 'aborted' };
      const raw = await safeGetItem('@boot/crash_count', '0', 500);
      const n = parseInt((raw as string) || '0', 10) || 0;
      return n < 3 ? { ok: true } : { ok: false, note: `count=${n}` };
    },
  },
  {
    id: 'backend', label: 'Backend connection', deps: ['finalize'],
    timeoutMs: 3_500, critical: false, weight: 30, phase: 1,
    retries: 0,
    run: async (signal) => {
      if (signal?.aborted) return { ok: false, note: 'aborted' };
      const r = await probeBackend(1, signal, 3_000);
      return r.ok ? { ok: true } : { ok: false, note: r.lastError || 'no response' };
    },
  },
  {
    id: 'feature_flags', label: 'Feature flags', deps: ['backend'],
    timeoutMs: 4_000, critical: false, weight: 10, phase: 1,
    retries: 1, backoffMs: 300,
    run: async (signal) => {
      if (signal?.aborted) return { ok: false, note: 'aborted' };
      const r = await api.get('/api/feature-flags', { timeoutMs: 4_000, retries: 1 });
      return r.ok ? { ok: true } : { ok: false, note: r.error || 'flags_failed' };
    },
  },
  {
    id: 'languages_prewarm', label: 'Workspace assets', deps: ['backend'],
    timeoutMs: 3_000, critical: false, weight: 15, phase: 1,
    run: async (signal) => {
      if (signal?.aborted) return { ok: false, note: 'aborted' };
      const r = await api.get('/api/languages', {
        timeoutMs: 2_500, retries: 0,
        cacheKey: 'languages', cacheTtlMs: 60_000,
      });
      return r.ok ? { ok: true } : { ok: true, note: 'skipped' };
    },
  },
  {
    id: 'tunnel_probe', label: 'Tunnel watchdog', deps: ['backend'],
    timeoutMs: 3_000, critical: false, weight: 5, phase: 1,
    run: async (signal) => {
      if (signal?.aborted) return { ok: false, note: 'aborted' };
      const r = await api.get('/api/health/tunnel', { timeoutMs: 2_500, retries: 0 });
      return r.ok ? { ok: true } : { ok: true, note: 'skipped' };
    },
  },
  {
    id: 'prune_storage', label: 'Pruning stale cache', deps: ['storage'],
    timeoutMs: 2_500, critical: false, weight: 5, phase: 2,
    run: async (signal) => {
      if (signal?.aborted) return { ok: false, note: 'aborted' };
      try {
        const r = await pruneExpired({ ttlMs: 7 * 24 * 60 * 60 * 1000 });
        return {
          ok: true,
          note: r.pruned > 0
            ? `pruned ${r.pruned}/${r.scanned} in ${r.elapsedMs}ms`
            : `clean (${r.scanned} keys, ${r.elapsedMs}ms)`,
        };
      } catch (e: any) {
        return { ok: true, note: `skipped: ${e?.message || 'error'}` };
      }
    },
  },
];

export const PLATFORM = Platform.OS;

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
import { getAppBootstrap, getAppRuntimeStatus } from '../product/appBootstrapClient';
import { loadFlags } from '../feature-flags/flagsClient';

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
  runtimeOk?: boolean;
  /** @deprecated retained for compatibility with pre-assembly boot caches */
  backendOk?: boolean;
}

export async function readBootCache(): Promise<CachedBoot | null> {
  try {
    const raw = await safeGetItem(BOOT_CACHE_KEY, null, 500);
    if (!raw) return null;
    const parsed = JSON.parse(raw as string);
    return parsed && typeof parsed === 'object' ? parsed as CachedBoot : null;
  } catch { return null; }
}

export async function writeBootCache(snapshot: CachedBoot): Promise<void> {
  try { await safeSetItem(BOOT_CACHE_KEY, JSON.stringify(snapshot)); } catch {}
}

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
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
      const key = `__boot_probe_${Date.now() % 1e6}`;
      await safeSetItem(key, '1', 600);
      const value = await safeGetItem(key, null, 600);
      return value === '1' ? { ok: true } : { ok: false, note: 'read-back failed' };
    },
  },
  {
    id: 'finalize', label: 'Finalizing', deps: ['storage'],
    timeoutMs: 200, critical: false, weight: 10, phase: 0,
    run: async (signal) => {
      try { await sleep(60, signal); } catch { return { ok: false, note: 'aborted' }; }
      return { ok: true };
    },
  },
  {
    id: 'crash_guard', label: 'Crash-loop guard', deps: ['storage'],
    timeoutMs: 700, critical: false, weight: 10, phase: 1,
    run: async (signal) => {
      if (signal?.aborted) return { ok: false, note: 'aborted' };
      const raw = await safeGetItem('@boot/crash_count', '0', 500);
      const count = parseInt((raw as string) || '0', 10) || 0;
      return count < 3 ? { ok: true } : { ok: false, note: `count=${count}` };
    },
  },
  {
    id: 'assembly_contract', label: 'Application contract', deps: ['finalize'],
    timeoutMs: 3_000, critical: false, weight: 10, phase: 1,
    retries: 0,
    run: async (signal) => {
      if (signal?.aborted) return { ok: false, note: 'aborted' };
      const bootstrap = await getAppBootstrap(signal);
      if (!bootstrap) return { ok: false, note: 'bootstrap unavailable' };
      if (bootstrap.application.name !== 'Skeleton') {
        return { ok: false, note: `identity=${bootstrap.application.name}` };
      }
      return {
        ok: true,
        note: `v${bootstrap.application.version} · ${bootstrap.profiles.default.services.length} services`,
      };
    },
  },
  {
    id: 'app_runtime', label: 'Application runtime', deps: ['assembly_contract'],
    timeoutMs: 4_000, critical: false, weight: 25, phase: 1,
    retries: 0,
    run: async (signal) => {
      if (signal?.aborted) return { ok: false, note: 'aborted' };
      const bootstrap = await getAppBootstrap(signal);
      if (!bootstrap) return { ok: false, note: 'bootstrap unavailable' };
      const runtime = await getAppRuntimeStatus(3_000, signal, bootstrap);
      if (!runtime) return { ok: false, note: 'runtime status unavailable' };
      const failed = runtime.services.filter(service => !service.ok).map(service => service.name);
      return runtime.ok
        ? { ok: true, note: `${runtime.services.length} services healthy` }
        : { ok: false, note: failed.length ? `degraded: ${failed.join(', ')}` : 'degraded' };
    },
  },
  {
    id: 'feature_flags', label: 'Feature flags', deps: ['app_runtime'],
    timeoutMs: 4_000, critical: false, weight: 10, phase: 1,
    retries: 0,
    run: async (signal) => {
      if (signal?.aborted) return { ok: false, note: 'aborted' };
      // Use the same user/keyed client as FeatureFlagProvider. If the provider
      // asks for flags while this request is running it reuses the in-flight
      // promise; if this finishes first, the provider consumes the warm cache.
      const snapshot = await loadFlags('default_user', { timeoutMs: 3_500, retries: 0 });
      return snapshot.ok ? { ok: true } : { ok: false, note: 'flags_failed' };
    },
  },
  {
    id: 'languages_prewarm', label: 'Workspace assets', deps: ['backend'],
    timeoutMs: 3_000, critical: false, weight: 15, phase: 1,
    run: async (signal) => {
      if (signal?.aborted) return { ok: false, note: 'aborted' };
      const result = await api.get('/api/languages', {
        timeoutMs: 2_500, retries: 0,
        cacheKey: 'languages', cacheTtlMs: 60_000,
      });
      return result.ok ? { ok: true } : { ok: true, note: 'skipped' };
    },
  },
  {
    id: 'tunnel_probe', label: 'Tunnel watchdog', deps: ['backend'],
    timeoutMs: 3_000, critical: false, weight: 5, phase: 1,
    run: async (signal) => {
      if (signal?.aborted) return { ok: false, note: 'aborted' };
      const result = await api.get('/api/health/tunnel', { timeoutMs: 2_500, retries: 0 });
      return result.ok ? { ok: true } : { ok: true, note: 'skipped' };
    },
  },
  {
    id: 'prune_storage', label: 'Pruning stale cache', deps: ['storage'],
    timeoutMs: 2_500, critical: false, weight: 5, phase: 2,
    run: async (signal) => {
      if (signal?.aborted) return { ok: false, note: 'aborted' };
      try {
        const result = await pruneExpired({ ttlMs: 7 * 24 * 60 * 60 * 1000 });
        return {
          ok: true,
          note: result.pruned > 0
            ? `pruned ${result.pruned}/${result.scanned} in ${result.elapsedMs}ms`
            : `clean (${result.scanned} keys, ${result.elapsedMs}ms)`,
        };
      } catch (error: any) {
        return { ok: true, note: `skipped: ${error?.message || 'error'}` };
      }
    },
  },
];

export const PLATFORM = Platform.OS;

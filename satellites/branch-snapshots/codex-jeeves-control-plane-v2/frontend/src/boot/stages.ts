/**
 * src/boot/stages.ts — declarative frontend boot stages (SOTA, May 2026 batch).
 *
 * Each stage:
 *   * id
 *   * label (user-visible)
 *   * deps[] (other stage IDs)
 *   * timeoutMs                 hard timeout for ONE attempt
 *   * critical                  if false, a failure is non-fatal
 *   * weight                    contributes to the boot score
 *   * phase                     0 (block-on-ready) / 1 (background) / 2 (lazy)
 *   * retries?                  NEW: max additional attempts after the first
 *                               failure. Default 0. Exponential backoff between
 *                               attempts: backoffMs * 2^(attempt-1).
 *   * backoffMs?                NEW: base backoff in ms (default 250).
 *   * run(signal?)              the actual async work; receives an AbortSignal
 *                               that the runner triggers on cancellation.
 *                               Stages should bail out promptly when the
 *                               signal aborts. Returns `{ ok, note? }`.
 *
 * The runner schedules stages in parallel, respecting ``deps`` and retrying
 * each failed attempt according to the stage's retry policy. Critical
 * failures abort their dependents.
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
  /** Max additional attempts after the first failure. Default 0. */
  retries?: number;
  /** Base backoff ms between attempts (exponential 2^n). Default 250. */
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

/** Lightweight signal-aware sleep (rejects on abort). */
function _sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(new Error('aborted'));
    const t = setTimeout(resolve, ms);
    const onAbort = () => { clearTimeout(t); reject(new Error('aborted')); };
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
    id: 'crash_guard', label: 'Crash-loop guard', deps: [],
    timeoutMs: 700, critical: false, weight: 10, phase: 0,
    run: async () => {
      const raw = await safeGetItem('@boot/crash_count', '0', 500);
      const n = parseInt((raw as string) || '0', 10) || 0;
      return n < 3 ? { ok: true } : { ok: false, note: `count=${n}` };
    },
  },
  {
    id: 'backend', label: 'Backend connection', deps: [],
    timeoutMs: 16_000, critical: false, weight: 30, phase: 0,
    retries: 0, backoffMs: 400,
    run: async (signal) => {
      if (signal?.aborted) return { ok: false, note: 'aborted' };
      // Cold-start tolerant: probeBackend bypasses the circuit breaker and
      // rides out a scale-to-zero wake. The stage timeout aborts via `signal`.
      const r = await probeBackend(6, signal);
      return r.ok ? { ok: true } : { ok: false, note: r.lastError || 'no response' };
    },
  },
  // ── Phase 1 (background) ────────────────────────────────────────────────
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
      return r.ok ? { ok: true } : { ok: true, note: 'skipped' };  // soft-fail — still OK
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
    id: 'finalize', label: 'Finalizing', deps: ['storage', 'backend'],
    timeoutMs: 400, critical: false, weight: 10, phase: 0,
    run: async (signal) => {
      try { await _sleep(220, signal); } catch { return { ok: false, note: 'aborted' }; }
      return { ok: true };
    },
  },
  // ── Phase 2 (lazy / post-launch housekeeping) ───────────────────────────
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
        return { ok: true, note: `skipped: ${e?.message || 'error'}` };  // soft-fail
      }
    },
  },
];

export const PLATFORM = Platform.OS;

/**
 * src/hooks/useOverview.ts — frontend handler for the central crosswire
 * control plane. One hook → one fetch → one rendering surface for the
 * status pill, debug screen, and audit grid.
 *
 * The endpoint behind this is /api/health/overview (added Feb 2026), which
 * aggregates state from routes_registry, build_watchdog, cold_storage,
 * databases, feature_flags, deprecations, and boot stages in a single
 * ≤250ms call. The frontend can poll it once every few seconds without
 * fanning out to N separate health endpoints.
 */

import { useEffect, useRef, useState } from 'react';
import api from '../utils/apiClient';

export interface OverviewSlot {
  ok: boolean;
  error?: string;
  [k: string]: any;
}

export interface OverviewPayload {
  process: {
    pid: number;
    python: string;
    started_at: number;
    uptime_s: number;
    deploy_env: 'dev' | 'production';
  };
  elapsed_ms: number;
  all_green: boolean;
  registry: OverviewSlot;
  watchdog: OverviewSlot;
  cold_storage: OverviewSlot;
  databases: OverviewSlot;
  feature_flags: OverviewSlot;
  deprecations: OverviewSlot;
  boot: OverviewSlot;
}

export interface UseOverviewOptions {
  /** Poll interval in ms. Default 15000 (15s). Set to 0 to disable polling. */
  intervalMs?: number;
  /** Whether to start polling immediately. Default true. */
  enabled?: boolean;
}

export function useOverview(opts: UseOverviewOptions = {}) {
  const { intervalMs = 15_000, enabled = true } = opts;
  const [data, setData] = useState<OverviewPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const mounted = useRef(true);

  const fetchOnce = async () => {
    if (!mounted.current) return;
    setLoading(true);
    const res = await api.get('/api/health/overview');
    if (!mounted.current) return;
    setLoading(false);
    if (res.ok) {
      setData(res.data as OverviewPayload);
      setError(null);
    } else {
      setError(res.error || `HTTP ${res.status}`);
    }
  };

  useEffect(() => {
    mounted.current = true;
    if (!enabled) return;
    fetchOnce();  // initial
    if (intervalMs <= 0) return;
    const t = setInterval(fetchOnce, intervalMs);
    return () => { mounted.current = false; clearInterval(t); };
     
  }, [enabled, intervalMs]);

  /** Refresh immediately without waiting for the next poll tick. */
  const refresh = () => fetchOnce();

  /** Derived: count of failing subsystems (0 when all_green). */
  const failingCount = data
    ? (['registry', 'watchdog', 'cold_storage', 'databases', 'feature_flags', 'deprecations', 'boot'] as const)
        .filter((k) => !data[k]?.ok).length
    : 0;

  /** Derived: colour token for a status pill. */
  const colour: 'green' | 'yellow' | 'red' | 'grey' =
    !data ? 'grey'
      : data.all_green ? 'green'
      : failingCount >= 3 ? 'red'
      : 'yellow';

  return {
    data,
    error,
    loading,
    refresh,
    failingCount,
    colour,
  };
}

export default useOverview;

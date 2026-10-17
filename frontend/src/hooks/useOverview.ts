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

import { useEffect } from 'react';
import api from '../utils/apiClient';
import { useQuery } from '../foundation/useQuery';
import {
  failingSubsystems, getJson, healthColour, overviewKey,
} from '../foundation/queries';
import type { OverviewPayload, OverviewSlot } from '../foundation/queries';

export type { OverviewPayload, OverviewSlot };

export interface UseOverviewOptions {
  /** Poll interval in ms. Default 15000 (15s). Set to 0 to disable polling. */
  intervalMs?: number;
  /** Whether to start polling immediately. Default true. */
  enabled?: boolean;
}

const fetchOverview = () => getJson<OverviewPayload>(api, '/api/health/overview');

/**
 * Backed by the shared foundation query cache: every caller shares one
 * request and one cached payload, with uniform loading/error state.
 */
export function useOverview(opts: UseOverviewOptions = {}) {
  const { intervalMs = 15_000, enabled = true } = opts;
  const query = useQuery(overviewKey, fetchOverview, { enabled, staleTimeMs: Math.max(1_000, intervalMs || 15_000) });
  const { refetch } = query;

  // TODO(realtime, slice 3): move live updates to useEventStream (SSE
  // /api/v1/events, PR #4101); keep this REST poll only as the fallback.
  useEffect(() => {
    if (!enabled || intervalMs <= 0) return;
    const timer = setInterval(() => { void refetch(); }, intervalMs);
    return () => clearInterval(timer);
  }, [enabled, intervalMs, refetch]);

  const data = query.data ?? null;
  return {
    data,
    error: query.error ? query.error.message : null,
    loading: query.fetching || query.status === 'loading',
    /** Refresh immediately without waiting for the next poll tick. */
    refresh: refetch,
    /** Derived: count of failing subsystems (0 when all_green). */
    failingCount: failingSubsystems(data).length,
    /** Derived: colour token for a status pill. */
    colour: healthColour(data),
    query,
  };
}

export default useOverview;

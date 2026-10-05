/**
 * src/utils/trailDump.ts — ship the local breadcrumb trail to
 * /api/telemetry/trail so server-side dashboards can replay the
 * sequence of actions that led to a crash.
 *
 * Called automatically by the ErrorBoundary when a render crashes;
 * may also be called manually for "send report" buttons.
 */
import api from './apiClient';
import { trail } from './breadcrumbs';

export interface DumpOpts {
  rid?: string | null;
  userAgent?: string;
}

export async function dumpTrail(opts: DumpOpts = {}): Promise<{ ok: boolean; buffered?: number; error?: string }> {
  const crumbs = trail.list ? trail.list() : (trail as any)._crumbs || [];
  if (!Array.isArray(crumbs) || crumbs.length === 0) {
    return { ok: true, buffered: 0 };
  }
  try {
    const r = await api.post<{ ok: boolean; buffered: number }>(
      '/api/telemetry/trail',
      { rid: opts.rid || null, user_agent: opts.userAgent || '', crumbs: crumbs.slice(-100) },
      { timeoutMs: 5_000, retries: 1 },
    );
    return { ok: !!r.ok, buffered: (r.data as any)?.buffered, error: r.error || undefined };
  } catch (e: any) {
    return { ok: false, error: e?.message || 'dump_failed' };
  }
}

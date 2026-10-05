/**
 * src/feature-flags/impressions.ts — client-side analytics for flag usage.
 *
 * Every render that reads a feature flag bumps an in-memory counter.
 * Every 30 s (or on `flush()`) we POST the batch to
 * /api/feature-flags/impressions so server-side dashboards can answer
 * "which flags are actually USED".
 *
 * Designed to be near-free: no I/O on the hot path, only on the 30 s
 * timer. Drops batches > 500 entries to bound memory.
 */
import api from '../utils/apiClient';

const FLUSH_INTERVAL_MS = 30_000;
const MAX_BATCH = 500;

interface Pending {
  name: string;
  value: boolean;
  count: number;
  first_seen: number;
}

const _pending: Map<string, Pending> = new Map();
let _timer: ReturnType<typeof setTimeout> | null = null;
let _started = false;

function _key(name: string, value: boolean): string { return `${name}|${value ? '1' : '0'}`; }

export function recordImpression(name: string, value: boolean): void {
  if (!name) return;
  const k = _key(name, value);
  const cur = _pending.get(k);
  if (cur) { cur.count += 1; }
  else {
    if (_pending.size >= MAX_BATCH) return;     // back-pressure
    _pending.set(k, { name, value, count: 1, first_seen: Date.now() });
  }
  _ensureTimer();
}

function _ensureTimer(): void {
  if (_timer) return;
  _timer = setTimeout(() => { _timer = null; void flush(); }, FLUSH_INTERVAL_MS);
}

export async function flush(): Promise<void> {
  if (_pending.size === 0) return;
  const rows = Array.from(_pending.values()).map(p => ({
    name: p.name, value: p.value, count: p.count, ts: p.first_seen,
  }));
  _pending.clear();
  try {
    await api.post('/api/feature-flags/impressions', { rows }, { timeoutMs: 5000, retries: 1 });
  } catch { /* swallow — analytics are best-effort */ }
}

export function start(): void {
  if (_started) return;
  _started = true;
  _ensureTimer();
}

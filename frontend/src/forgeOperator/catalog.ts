/**
 * Era, generation, beat and execution view-models for the operator screens.
 *
 * Era rows come from `GET /api/skeleton/eras` (compiled dialect packs),
 * generations from `/api/skeleton/generations`, questionnaire beats from
 * `/api/skeleton/beats`, and governed executions from the product-control
 * cockpit projection. Everything here is pure so it is unit-tested against
 * captured backend fixtures.
 */
import type { Beat, EraRow, ExecutionProjection, GenerationRow } from './types';

// ── Eras ───────────────────────────────────────────────────────────────

export type EraMetric = 'primary_dps' | 'speed' | 'trash' | 'elite' | 'boss' | 'player_glass';

export const ERA_METRICS: { key: EraMetric; label: string; unit: string }[] = [
  { key: 'primary_dps', label: 'Primary DPS', unit: '' },
  { key: 'speed', label: 'Move speed', unit: 'px/s' },
  { key: 'trash', label: 'Trash TTK', unit: 's' },
  { key: 'elite', label: 'Elite TTK', unit: 's' },
  { key: 'boss', label: 'Boss TTK', unit: 's' },
  { key: 'player_glass', label: 'Player glass', unit: 's' },
];

export function eraMetric(row: EraRow, key: EraMetric): number {
  if (key === 'primary_dps') return row.primary_dps;
  if (key === 'speed') return row.speed;
  const v = row.ttk?.[key];
  return typeof v === 'number' ? v : NaN;
}

export interface Extent { min: number; max: number }

export function eraExtents(rows: EraRow[]): Record<EraMetric, Extent> {
  const out = {} as Record<EraMetric, Extent>;
  for (const { key } of ERA_METRICS) {
    const values = rows.map((r) => eraMetric(r, key)).filter((n) => Number.isFinite(n));
    out[key] = values.length ? { min: Math.min(...values), max: Math.max(...values) } : { min: 0, max: 0 };
  }
  return out;
}

/** 0..1 position of a value inside its extent (0.5 when the extent is flat). */
export function normalise(value: number, extent: Extent): number {
  if (!Number.isFinite(value)) return 0;
  const span = extent.max - extent.min;
  return span > 0 ? (value - extent.min) / span : 0.5;
}

export function filterEras(rows: EraRow[], query: string): EraRow[] {
  const q = query.trim().toLowerCase();
  if (!q) return rows;
  return rows.filter((r) => r.id.toLowerCase().includes(q) || (r.philosophy || '').toLowerCase().includes(q));
}

export function sortEras(rows: EraRow[], key: EraMetric | 'id', descending = true): EraRow[] {
  const copy = [...rows];
  if (key === 'id') return copy.sort((a, b) => a.id.localeCompare(b.id));
  return copy.sort((a, b) => {
    const d = eraMetric(a, key) - eraMetric(b, key);
    return (descending ? -d : d) || a.id.localeCompare(b.id);
  });
}

export interface EraDelta { key: EraMetric; label: string; a: number; b: number; ratio: number | null }

/** Metric-by-metric comparison of two eras (ratio = b / a). */
export function compareEras(a: EraRow, b: EraRow): EraDelta[] {
  return ERA_METRICS.map(({ key, label }) => {
    const va = eraMetric(a, key);
    const vb = eraMetric(b, key);
    return { key, label, a: va, b: vb, ratio: Number.isFinite(va) && va !== 0 && Number.isFinite(vb) ? vb / va : null };
  });
}

/**
 * Linear estimate of a blend at t. The engine's `blend_eras` also lerps the
 * compiled packs before re-deriving HP, so DPS/speed/TTK track this closely;
 * the screen labels it an estimate and the real numbers come from /plan.
 */
export function blendEstimate(a: EraRow, b: EraRow, t: number): Record<EraMetric, number> {
  const tt = Math.min(1, Math.max(0, t));
  const out = {} as Record<EraMetric, number>;
  for (const { key } of ERA_METRICS) {
    const va = eraMetric(a, key);
    const vb = eraMetric(b, key);
    out[key] = va + (vb - va) * tt;
  }
  return out;
}

/** Eras grouped by design philosophy, largest group first. */
export function philosophyGroups(rows: EraRow[]): { philosophy: string; eras: string[] }[] {
  const groups = new Map<string, string[]>();
  for (const r of rows) {
    const key = r.philosophy || 'unspecified';
    groups.set(key, [...(groups.get(key) ?? []), r.id]);
  }
  return Array.from(groups, ([philosophy, eras]) => ({ philosophy, eras })).sort(
    (x, y) => y.eras.length - x.eras.length || x.philosophy.localeCompare(y.philosophy),
  );
}

// ── Generations ────────────────────────────────────────────────────────

export function generationLadder(rows: GenerationRow[]): GenerationRow[] {
  return [...rows].sort((a, b) => (a.order ?? 0) - (b.order ?? 0) || a.key.localeCompare(b.key));
}

// ── Questionnaire beats ────────────────────────────────────────────────

/** Beat whose answer names the era directly; "unspecified" means let intake vote. */
export const EXPLICIT_ERA_BEAT = 'era_explicit';
export const UNSPECIFIED = 'unspecified';

export interface BeatProgress { answered: number; total: number; missing: string[] }

export function beatProgress(beats: Beat[], answers: Record<string, string>): BeatProgress {
  const required = beats.filter((b) => b.id !== EXPLICIT_ERA_BEAT);
  const missing = required.filter((b) => !answers[b.id]).map((b) => b.id);
  return { answered: required.length - missing.length, total: required.length, missing };
}

/**
 * Answers exactly as the engine should receive them: unknown beats and
 * options dropped, the explicit-era beat omitted when "unspecified".
 */
export function cleanAnswers(beats: Beat[], answers: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const beat of beats) {
    const value = answers[beat.id];
    if (!value || !beat.options.includes(value)) continue;
    if (beat.id === EXPLICIT_ERA_BEAT && value === UNSPECIFIED) continue;
    out[beat.id] = value;
  }
  return out;
}

/** Deterministic pseudo-random answers (mulberry32) for "surprise me". */
export function seededAnswers(beats: Beat[], seed: number): Record<string, string> {
  let s = seed >>> 0;
  const next = () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  const out: Record<string, string> = {};
  for (const beat of beats) {
    if (!beat.options.length) continue;
    out[beat.id] = beat.id === EXPLICIT_ERA_BEAT ? UNSPECIFIED : beat.options[Math.floor(next() * beat.options.length)];
  }
  return out;
}

/** Ballots sorted by votes with the share each era received. */
export function ballotShares(ballots: Record<string, number> | null | undefined): { era: string; votes: number; share: number }[] {
  const entries = Object.entries(ballots ?? {}).filter(([, v]) => typeof v === 'number' && v > 0);
  const total = entries.reduce((n, [, v]) => n + v, 0);
  return entries
    .map(([era, votes]) => ({ era, votes, share: total ? votes / total : 0 }))
    .sort((a, b) => b.votes - a.votes || a.era.localeCompare(b.era));
}

// ── Governed executions ────────────────────────────────────────────────

export type ExecutionTone = 'ok' | 'pending' | 'stuck' | 'anomalous';

/** How an operator should read one projected execution. */
export function executionTone(e: ExecutionProjection): ExecutionTone {
  if (e.anomalyCount > 0) return 'anomalous';
  if (e.pending && !e.executorBound) return 'stuck';
  if (e.pending) return 'pending';
  return 'ok';
}

export interface ExecutionSummary {
  total: number;
  byState: { state: string; count: number }[];
  byTone: Record<ExecutionTone, number>;
  anomalies: { code: string; count: number }[];
  lowConfidence: number;
}

export function summariseExecutions(list: ExecutionProjection[]): ExecutionSummary {
  const states = new Map<string, number>();
  const anomalies = new Map<string, number>();
  const byTone: Record<ExecutionTone, number> = { ok: 0, pending: 0, stuck: 0, anomalous: 0 };
  let lowConfidence = 0;
  for (const e of list) {
    states.set(e.state, (states.get(e.state) ?? 0) + 1);
    byTone[executionTone(e)] += 1;
    if (e.confidence === 'low') lowConfidence += 1;
    for (const a of e.anomalies) anomalies.set(a, (anomalies.get(a) ?? 0) + 1);
  }
  const sortDesc = <T extends { count: number }>(xs: T[], key: (x: T) => string) =>
    xs.sort((a, b) => b.count - a.count || key(a).localeCompare(key(b)));
  return {
    total: list.length,
    byState: sortDesc(Array.from(states, ([state, count]) => ({ state, count })), (x) => x.state),
    byTone,
    anomalies: sortDesc(Array.from(anomalies, ([code, count]) => ({ code, count })), (x) => x.code),
    lowConfidence,
  };
}

/** Tone order for the list: things that need a human first. */
export function sortExecutions(list: ExecutionProjection[]): ExecutionProjection[] {
  const rank: Record<ExecutionTone, number> = { anomalous: 0, stuck: 1, pending: 2, ok: 3 };
  return [...list].sort((a, b) => rank[executionTone(a)] - rank[executionTone(b)] || a.operationId.localeCompare(b.operationId));
}

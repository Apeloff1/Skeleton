/**
 * Pure era catalog view-model helpers for ErasPanel / tests.
 * Shapes match EraRow in types.ts. Mirrors planSummary / beatSummary / walkSummary.
 */
import type { EraRow } from './types';

export interface EraSummary {
  id: string;
  philosophy: string;
  philosophyLabel: string;
  statsLabel: string;
  ttkLabel: string;
  dps: number;
  speed: number;
}

export interface ErasCatalogSummary {
  count: number;
  philosophies: string[];
  fastestId: string | null;
  glassiestId: string | null;
}

export interface EraFilter {
  query?: string | null;
  philosophy?: string | null;
}

type EraTtk = EraRow['ttk'];

function finite(n: unknown): number | null {
  return typeof n === 'number' && Number.isFinite(n) ? n : null;
}

/** Trim trailing zeros: 60 → "60", 1.1 → "1.1", 1.80 → "1.8". */
function fmtNum(n: number): string {
  if (!Number.isFinite(n)) return '—';
  if (Number.isInteger(n) || Math.abs(n - Math.round(n)) < 1e-9) return String(Math.round(n));
  return String(Number(n.toFixed(2)));
}

function fmtSec(n: number): string {
  return `${fmtNum(n)}s`;
}

/** e.g. "trash 1.1s · elite 4.5s · boss 60s · glass 1.8s" (omit missing; em dash if empty). */
export function formatTtk(ttk: EraTtk | null | undefined): string {
  if (!ttk || typeof ttk !== 'object') return '—';
  const parts: string[] = [];
  const trash = finite(ttk.trash);
  const elite = finite(ttk.elite);
  const boss = finite(ttk.boss);
  const glass = finite(ttk.player_glass);
  if (trash != null) parts.push(`trash ${fmtSec(trash)}`);
  if (elite != null) parts.push(`elite ${fmtSec(elite)}`);
  if (boss != null) parts.push(`boss ${fmtSec(boss)}`);
  if (glass != null) parts.push(`glass ${fmtSec(glass)}`);
  return parts.length ? parts.join(' · ') : '—';
}

/** e.g. "DPS 108 · speed 195". */
export function formatEraStats(era: EraRow | null | undefined): string {
  if (!era) return '—';
  const dps = finite(era.primary_dps);
  const speed = finite(era.speed);
  if (dps == null && speed == null) return '—';
  const parts: string[] = [];
  if (dps != null) parts.push(`DPS ${fmtNum(dps)}`);
  if (speed != null) parts.push(`speed ${fmtNum(speed)}`);
  return parts.join(' · ');
}

/** Replace underscores with spaces. */
export function humanizePhilosophy(p: string | null | undefined): string {
  if (p == null || typeof p !== 'string') return '';
  return p.replace(/_/g, ' ').trim();
}

/** Sorted unique raw philosophy strings. */
export function listPhilosophies(eras: EraRow[] | null | undefined): string[] {
  if (!eras?.length) return [];
  const set = new Set<string>();
  for (const e of eras) {
    if (e?.philosophy && typeof e.philosophy === 'string') set.add(e.philosophy);
  }
  return [...set].sort((a, b) => a.localeCompare(b));
}

/** Case-insensitive id / philosophy match; optional exact philosophy filter. */
export function filterEras(eras: EraRow[] | null | undefined, filter: EraFilter | null | undefined): EraRow[] {
  const list = Array.isArray(eras) ? eras.filter((e) => e && typeof e.id === 'string') : [];
  if (!filter) return list;
  const q = (filter.query ?? '').trim().toLowerCase();
  const phil = (filter.philosophy ?? '').trim().toLowerCase();
  return list.filter((e) => {
    if (phil && String(e.philosophy ?? '').toLowerCase() !== phil) return false;
    if (!q) return true;
    const hay = `${e.id} ${e.philosophy ?? ''}`.toLowerCase();
    return hay.includes(q);
  });
}

/** Null-safe single-era readout. */
export function summarizeEra(era: EraRow | null | undefined): EraSummary | null {
  if (!era || typeof era.id !== 'string' || !era.id) return null;
  const dps = finite(era.primary_dps) ?? 0;
  const speed = finite(era.speed) ?? 0;
  const philosophy = typeof era.philosophy === 'string' ? era.philosophy : '';
  return {
    id: era.id,
    philosophy,
    philosophyLabel: humanizePhilosophy(philosophy) || '—',
    statsLabel: formatEraStats(era),
    ttkLabel: formatTtk(era.ttk),
    dps,
    speed,
  };
}

/**
 * Catalog-level summary. fastestId = max speed; glassiestId = min player_glass
 * among eras that have it. Ties keep the first occurrence in input order.
 */
export function summarizeErasCatalog(eras: EraRow[] | null | undefined): ErasCatalogSummary {
  const list = Array.isArray(eras) ? eras.filter((e) => e && typeof e.id === 'string') : [];
  let fastestId: string | null = null;
  let fastestSpeed = -Infinity;
  let glassiestId: string | null = null;
  let glassiest = Infinity;
  for (const e of list) {
    const speed = finite(e.speed);
    if (speed != null && speed > fastestSpeed) {
      fastestSpeed = speed;
      fastestId = e.id;
    }
    const glass = finite(e.ttk?.player_glass);
    if (glass != null && glass < glassiest) {
      glassiest = glass;
      glassiestId = e.id;
    }
  }
  return {
    count: list.length,
    philosophies: listPhilosophies(list),
    fastestId,
    glassiestId,
  };
}

/**
 * Era viewer view-model over GET /api/skeleton/eras.
 */
import type { EraRow } from './types';
import { humanize } from './graph';

export type EraSortKey = 'name' | 'dps' | 'speed' | 'ttk';

export const ERA_SORTS: readonly { id: EraSortKey; label: string }[] = [
  { id: 'name', label: 'Name' },
  { id: 'dps', label: 'DPS' },
  { id: 'speed', label: 'Speed' },
  { id: 'ttk', label: 'Trash TTK' },
];

export interface EraView {
  id: string;
  label: string;
  philosophy: string;
  dps: number;
  speed: number;
  ttkTrash: number | null;
  ttkElite: number | null;
  ttkBoss: number | null;
  /** 0..1 relative to the strongest era in the list. */
  dpsRatio: number;
  speedRatio: number;
  ttkRatio: number;
}

const n = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);

export function eraViews(rows: EraRow[] | null | undefined): EraView[] {
  const list = (rows ?? []).filter((r) => r && typeof r.id === 'string');
  const maxDps = Math.max(1, ...list.map((r) => n(r.primary_dps) ?? 0));
  const maxSpeed = Math.max(1, ...list.map((r) => n(r.speed) ?? 0));
  const maxTtk = Math.max(0.001, ...list.map((r) => n(r.ttk?.trash) ?? 0));
  return list.map((r) => {
    const dps = n(r.primary_dps) ?? 0;
    const speed = n(r.speed) ?? 0;
    const trash = n(r.ttk?.trash);
    return {
      id: r.id,
      label: humanize(r.id),
      philosophy: humanize(String(r.philosophy ?? '')),
      dps,
      speed,
      ttkTrash: trash,
      ttkElite: n(r.ttk?.elite),
      ttkBoss: n(r.ttk?.boss),
      dpsRatio: dps / maxDps,
      speedRatio: speed / maxSpeed,
      ttkRatio: trash === null ? 0 : trash / maxTtk,
    };
  });
}

export function filterEras(views: EraView[], query: string): EraView[] {
  const q = query.trim().toLowerCase();
  if (!q) return views;
  return views.filter((v) => `${v.id} ${v.label} ${v.philosophy}`.toLowerCase().includes(q));
}

export function sortEras(views: EraView[], key: EraSortKey): EraView[] {
  const out = [...views];
  const by: Record<EraSortKey, (a: EraView, b: EraView) => number> = {
    name: (a, b) => a.label.localeCompare(b.label),
    dps: (a, b) => b.dps - a.dps || a.label.localeCompare(b.label),
    speed: (a, b) => b.speed - a.speed || a.label.localeCompare(b.label),
    ttk: (a, b) => (a.ttkTrash ?? Infinity) - (b.ttkTrash ?? Infinity) || a.label.localeCompare(b.label),
  };
  return out.sort(by[key]);
}

/** Blend ids look like "a~b@0.50"; resolve the base era for highlighting. */
export function baseEra(id: string | null | undefined): string | null {
  if (!id) return null;
  return String(id).split('~')[0].split('@')[0] || null;
}

export function describeEra(v: EraView): string {
  const ttk = v.ttkTrash === null ? 'unknown' : `${v.ttkTrash}s`;
  return `${v.label}: ${v.philosophy || 'no stated philosophy'}; primary DPS ${v.dps}, move speed ${v.speed}, trash time-to-kill ${ttk}.`;
}

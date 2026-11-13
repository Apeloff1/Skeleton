/** Stable offline-first Galaxy genre registry.
 *
 * The live catalog is advisory. A truncated/stale API response must never
 * hide any recovered historical genre. New backend entries must be shaped
 * and bounded before entering a mobile/UI render or draft handoff.
 */
import { FALLBACK_GENRES, type FallbackGenre } from './fallbackGenres';

export const GALAXY_LIVE_GENRE_LIMIT = 512;
export const GALAXY_SUBGENRE_LIMIT = 80;

const ID = /^[a-z][a-z0-9_-]{0,63}$/;
const COLOR = /^#[0-9a-fA-F]{6}$/;
const safeInt = (value: unknown, fallback: number): number =>
  Number.isSafeInteger(value) && (value as number) >= 0 && (value as number) <= 20_000
    ? value as number : fallback;
const safeText = (value: unknown, max: number, fallback: string): string =>
  typeof value === 'string' && value.trim() && value.length <= max ? value.trim() : fallback;
const isRecord = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value);

function normalizeLiveGenre(value: unknown, fallback?: FallbackGenre): FallbackGenre | null {
  if (!isRecord(value) || typeof value.id !== 'string' || !ID.test(value.id)) return null;
  const subgenres: string[] = [];
  const seen = new Set<string>();
  if (Array.isArray(value.subgenres)) {
    for (const item of value.subgenres) {
      if (subgenres.length >= GALAXY_SUBGENRE_LIMIT) break;
      if (typeof item !== 'string' || !ID.test(item) || seen.has(item)) continue;
      seen.add(item);
      subgenres.push(item);
    }
  }
  const selected = subgenres.length > 0 ? subgenres : fallback?.subgenres ?? [];
  return {
    id: value.id,
    name: safeText(value.name, 120, fallback?.name ?? value.id.replace(/_/g, ' ')),
    icon: safeText(value.icon, 16, fallback?.icon ?? '🎮'),
    color: typeof value.color === 'string' && COLOR.test(value.color)
      ? value.color : fallback?.color ?? '#64748B',
    desc: safeText(value.desc, 500, fallback?.desc ?? ''),
    screens: safeInt(value.screens, fallback?.screens ?? 0),
    components: safeInt(value.components, fallback?.components ?? 0),
    logic_files: safeInt(value.logic_files, fallback?.logic_files ?? 0),
    subgenres: selected,
    subgenre_count: selected.length,
  };
}

export function mergeGalaxyGenreCatalog(live: unknown): FallbackGenre[] {
  const rows = isRecord(live) && Array.isArray(live.genres) ? live.genres : [];
  const catalog = new Map<string, FallbackGenre>(FALLBACK_GENRES.map(genre => [genre.id, genre]));
  // Historical entries remain first and retain their ordering even if a
  // live response is incomplete. Duplicate live IDs cannot occupy two slots.
  for (const item of rows.slice(0, GALAXY_LIVE_GENRE_LIMIT)) {
    const id = isRecord(item) ? item.id : null;
    if (typeof id !== 'string') continue;
    const normalized = normalizeLiveGenre(item, catalog.get(id));
    if (normalized) catalog.set(id, normalized);
  }
  return [...catalog.values()];
}

/** Selector requests a saved remote genre only once it appears in the
 *  validated merged catalog. Never substitute an unrelated default genre.
 */
export function recoveredGalaxyGenre(catalog: readonly FallbackGenre[], id: string | null | undefined): FallbackGenre | null {
  if (typeof id !== 'string' || !ID.test(id)) return null;
  return catalog.find((entry) => entry.id === id) ?? null;
}

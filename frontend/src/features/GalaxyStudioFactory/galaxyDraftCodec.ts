/** Full-fidelity Galaxy editor draft custody on explicit cross-studio navigation.
 * Saves authored controls, 14 matrix tensor families and 100 extra sliders locally.
 * Does not infer that Galaxy slider semantics equal GameForge's ten design axes.
 * No network and no automatic game creation.
 */

export const GALAXY_DRAFT_SCHEMA = 'skeleton.galaxy.editor-draft.v1' as const;
export const GALAXY_DRAFT_MAX_BYTES = 320 * 1024;
export const GALAXY_DRAFT_TTL_MS = 30 * 24 * 60 * 60 * 1000;
const KEY_PATTERN = /^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$/;
const MATRIX_FAMILIES = new Set([
  'mechanics', 'world', 'art', 'audio', 'tech', 'monetisation', 'qa', 'agent',
  'vector_db', 'plagiarism', 'rdbms', 'styles', 'mutation', 'unique_flair',
]);
const STYLE_ENUMS: Record<string, readonly string[]> = {
  animationStyle: ['subtle', 'smooth', 'punchy', 'cinematic'],
  storylineStyle: ['heroic', 'tragedy', 'mystery', 'redemption', 'coming_of_age', 'comedy', 'cosmic_horror'],
  gamePace: ['slow_burn', 'standard', 'action_packed', 'breakneck'],
  difficultyCurve: ['gentle', 'steady', 'adaptive', 'punishing'],
  perspective: ['first_person', 'third_person', 'isometric', 'top_down', 'side_scroll', 'vr'],
  combatStyle: ['realtime', 'turn_based', 'action_rpg', 'rhythm', 'tactical', 'none'],
  visualStyle: ['photoreal', 'cel_shaded', 'pixel_art', 'low_poly', 'voxel', 'hand_painted', 'anime'],
  gameTone: ['heroic', 'dark', 'humorous', 'melancholic', 'epic', 'cozy', 'unsettling'],
  progressionType: ['linear', 'open_world', 'metroidvania', 'roguelike', 'sandbox', 'hub_and_spoke'],
  audioMood: ['orchestral', 'synthwave', 'ambient', 'chiptune', 'rock', 'folk', 'silent'],
  locomotionStyle: ['basic', 'tactical', 'parkour', 'als', 'gunplay', 'melee'],
};

export interface GalaxyDraftSnapshot {
  schema: typeof GALAXY_DRAFT_SCHEMA;
  savedMs: number;
  title: string;
  gameVision: string;
  systemArch: string;
  worldLaws: string;
  agentInstructions: string;
  genreId: string | null;
  subgenreId: string | null;
  extraGenreIds: string[];
  extraSubgenreIds: string[];
  multiGenreMode: boolean;
  quickMode: boolean;
  complexity: number;
  ageTarget: string;
  selectedEraId: string;
  ageEraYear: number;
  classic: Record<string, number>;
  styleChoices: Record<string, string | boolean>;
  styleParams: Record<string, string>;
  extraParams: Record<string, number>;
  production: {
    sliders: Record<string, number>;
    platforms: string[];
    languages: string[];
    monetization: string;
    saveSystem: string;
    networkMode: string;
    artDirection: string;
    gameTone: string;
    narrativeStructure: string;
    perspective: string;
  };
  matrices: Record<string, Record<string, Record<string, number>>>;
  narrative: Record<string, Record<string, number>>;
}

const obj = (x: unknown): Record<string, unknown> | null =>
  x !== null && typeof x === 'object' && !Array.isArray(x) ? x as Record<string, unknown> : null;
const clip = (x: unknown, limit: number): string => typeof x === 'string' ? x.slice(0, limit) : '';
const validId = (x: unknown): x is string => typeof x === 'string' && KEY_PATTERN.test(x);
const num = (x: unknown, lo: number, hi: number, fallback: number): number =>
  typeof x === 'number' && Number.isFinite(x) && x >= lo && x <= hi ? x : fallback;

function numericMap(raw: unknown, max: number, lo: number, hi: number): Record<string, number> {
  const source = obj(raw), out: Record<string, number> = {};
  if (!source) return out;
  let count = 0;
  for (const [key, value] of Object.entries(source)) {
    if (count >= max) break;
    if (!KEY_PATTERN.test(key) || ['constructor','prototype','__proto__'].includes(key)) continue;
    if (typeof value === 'number' && Number.isFinite(value) && value >= lo && value <= hi) {
      out[key] = value; count++;
    }
  }
  return out;
}

function stringMap(raw: unknown, max: number): Record<string, string> {
  const source = obj(raw), out: Record<string, string> = {};
  if (!source) return out;
  let count = 0;
  for (const [key, value] of Object.entries(source)) {
    if (count >= max) break;
    if (KEY_PATTERN.test(key) && typeof value === 'string' &&
        value.length <= 120 && !['constructor','prototype','__proto__'].includes(key)) {
      out[key] = value; count++;
    }
  }
  return out;
}
function idArray(raw: unknown, max = 80): string[] {
  if (!Array.isArray(raw)) return [];
  return [...new Set(raw.filter(validId).slice(0, max))];
}
function matricesFrom(raw: unknown): GalaxyDraftSnapshot['matrices'] {
  const source = obj(raw), out: GalaxyDraftSnapshot['matrices'] = {};
  if (!source) return out;
  for (const [family, phases] of Object.entries(source)) {
    if (!MATRIX_FAMILIES.has(family)) continue;
    const phaseSet = obj(phases);
    if (!phaseSet) continue;
    const sanitized: Record<string, Record<string, number>> = {};
    let count = 0;
    for (const [phase, axes] of Object.entries(phaseSet)) {
      if (count >= 128) break;
      if (!validId(phase)) continue;
      sanitized[phase] = numericMap(axes, 16, 0, 1000);
      count++;
    }
    out[family] = sanitized;
  }
  return out;
}

export function normalizeGalaxyDraft(raw: unknown, now: number = Date.now()): GalaxyDraftSnapshot | null {
  const v = obj(raw);
  if (!v || v.schema !== GALAXY_DRAFT_SCHEMA ||
      typeof v.savedMs !== 'number' || !Number.isSafeInteger(v.savedMs) ||
      !Number.isFinite(now) || v.savedMs > now + 30_000 ||
      now - v.savedMs > GALAXY_DRAFT_TTL_MS) return null;
  const production = obj(v.production) ?? {};
  const styles = obj(v.styleChoices) ?? {};
  const styleChoices: Record<string, string | boolean> = {};
  for (const [key, value] of Object.entries(styles).slice(0, 20)) {
    if (!KEY_PATTERN.test(key) || ['constructor','prototype','__proto__'].includes(key)) continue;
    if (key === 'cameraEffects') {
      if (typeof value === 'boolean') styleChoices[key] = value;
    } else if (typeof value === 'string' && STYLE_ENUMS[key]?.includes(value)) {
      styleChoices[key] = value;
    }
  }
  const narrative: GalaxyDraftSnapshot['narrative'] = {};
  const phaseSet = obj(v.narrative);
  if (phaseSet) {
    for (const [phase, axes] of Object.entries(phaseSet).slice(0, 100)) {
      if (validId(phase)) narrative[phase] = numericMap(axes, 8, 0, 1000);
    }
  }
  return {
    schema: GALAXY_DRAFT_SCHEMA, savedMs: v.savedMs,
    title: clip(v.title, 160), gameVision: clip(v.gameVision, 4000),
    systemArch: clip(v.systemArch, 4000), worldLaws: clip(v.worldLaws, 4000),
    agentInstructions: clip(v.agentInstructions, 4000),
    genreId: validId(v.genreId) ? v.genreId : null,
    subgenreId: validId(v.subgenreId) ? v.subgenreId : null,
    extraGenreIds: idArray(v.extraGenreIds), extraSubgenreIds: idArray(v.extraSubgenreIds),
    multiGenreMode: v.multiGenreMode === true,
    quickMode: v.quickMode === true,
    complexity: num(v.complexity, 0, 10, 10),
    ageTarget: clip(v.ageTarget, 32) || 'ALL',
    selectedEraId: validId(v.selectedEraId) ? v.selectedEraId : 'ps5_2020',
    ageEraYear: num(v.ageEraYear, 1985, 2030, 2025),
    classic: numericMap(v.classic, 48, 0, 10),
    styleChoices, styleParams: stringMap(v.styleParams, 32),
    extraParams: numericMap(v.extraParams, 180, 0, 1000),
    production: {
      sliders: numericMap(production.sliders, 200, 0, 100),
      platforms: idArray(production.platforms, 40),
      languages: idArray(production.languages, 80),
      monetization: clip(production.monetization, 80),
      saveSystem: clip(production.saveSystem, 80),
      networkMode: clip(production.networkMode, 80),
      artDirection: clip(production.artDirection, 80),
      gameTone: clip(production.gameTone, 80),
      narrativeStructure: clip(production.narrativeStructure, 80),
      perspective: clip(production.perspective, 80),
    },
    matrices: matricesFrom(v.matrices), narrative,
  };
}


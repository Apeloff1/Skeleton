/**
 * Original Galaxy Studio -> GameForge handoff. Pure, bounded, versioned.
 *
 * One-use, same-runtime handoffs are deliberate: local app navigation is not
 * an account-authenticated project store. The complete authoring snapshot
 * is carried through the next GameForge run and emitted as a project artifact.
 */
import { galaxyGenre, mappedBriefGenre } from './galaxyGenres';

export const GALAXY_PROFILE_SCHEMA = 'skeleton.gameforge.galaxy_profile.v1' as const;
export const MATRIX_FIELDS = [
  'mechanics_matrix', 'world_matrix', 'art_matrix', 'audio_matrix',
  'tech_matrix', 'monetisation_matrix', 'qa_matrix', 'agent_matrix',
  'vector_db_matrix', 'plagiarism_matrix', 'rdbms_matrix', 'styles_matrix',
  'mutation_matrix', 'unique_flair_matrix',
] as const;
export const MAX_PROFILE_CHARS = 450_000;
export const PROFILE_TTL_MS = 10 * 60 * 1000;
const MAX_FIELDS = 24_000;
const MAX_DEPTH = 9;

export interface GalaxyProfile {
  schema: typeof GALAXY_PROFILE_SCHEMA;
  config: Record<string, unknown>;
}
export interface GalaxyPrefill {
  vision: string;
  genre: string | null;
  mappedGenre: string | null;
  axes: Record<string, number>;
  profile: GalaxyProfile;
}

function fail(detail: string): never {
  throw new Error('Galaxy questionnaire transfer rejected: ' + detail);
}
function plain(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object'
    && !Array.isArray(value) && (Object.getPrototypeOf(value) === Object.prototype
    || Object.getPrototypeOf(value) === null);
}
function guard(value: unknown, budget: { count: number }, depth: number): void {
  if (++budget.count > MAX_FIELDS || depth > MAX_DEPTH) fail('configuration exceeds allowed complexity');
  if (value === null || typeof value === 'boolean') return;
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) fail('non-finite slider value');
    return;
  }
  if (typeof value === 'string') {
    if (value.length > 12_000) fail('a text field exceeds its maximum length');
    return;
  }
  if (Array.isArray(value)) {
    if (value.length > 4_096) fail('array exceeds limit');
    for (const entry of value) guard(entry, budget, depth + 1);
    return;
  }
  if (!plain(value)) fail('non-JSON data is forbidden');
  const entries = Object.entries(value);
  if (entries.length > 4_096) fail('object exceeds limit');
  for (const [key, entry] of entries) {
    if (!/^[a-zA-Z][a-zA-Z0-9_.-]{0,127}$/.test(key) || ['__proto__', 'constructor', 'prototype'].includes(key)) {
      fail('invalid configuration key');
    }
    guard(entry, budget, depth + 1);
  }
}

export function normaliseGalaxyProfile(payload: unknown): GalaxyProfile {
  if (!plain(payload) || typeof payload.title !== 'string' || !payload.title.trim()
      || payload.title.length > 120 || typeof payload.genre !== 'string'
      || !payload.genre || payload.genre.length > 128) fail('missing game title or genre');
  for (const field of MATRIX_FIELDS) if (!plain(payload[field])) fail('missing ' + field);
  if (!plain(payload.narrative_phases) || !plain(payload.extra_params) || !plain(payload.style_params)) {
    fail('missing narrative, extended or style controls');
  }
  guard(payload, { count: 0 }, 0);
  let serialized = '';
  try { serialized = JSON.stringify(payload); } catch { fail('non-serializable input'); }
  if (!serialized || serialized.length > MAX_PROFILE_CHARS) fail('configuration exceeds 450 KB');
  // Defensive clone protects the snapshot against both subsequent UI editing
  // and a caller mutating a returned value before its one-use consumption.
  return { schema: GALAXY_PROFILE_SCHEMA, config: JSON.parse(serialized) };
}

let pending: { id: string; value: GalaxyProfile; expires: number } | null = null;
let sequence = 0;

export function prepareGalaxyHandoff(payload: unknown, now: number = Date.now()): string {
  if (!Number.isFinite(now)) fail('invalid clock');
  const value = normaliseGalaxyProfile(payload);
  // ID is only a routing hint. It is NOT an authorization token. Data lives
  // only in JS memory, never in localStorage/AsyncStorage or a public URL.
  const id = 'g' + now.toString(36) + 'x' + (++sequence).toString(36);
  pending = { id, value, expires: now + PROFILE_TTL_MS };
  return id;
}

export function consumeGalaxyHandoff(id: string | null | undefined, now: number = Date.now()): GalaxyProfile | null {
  if (!id || !pending || id !== pending.id) return null;
  const captured = pending;
  pending = null;
  if (!Number.isFinite(now) || now > captured.expires) return null;
  return normaliseGalaxyProfile(captured.value.config);
}

const numeric = (v: unknown): number | null => typeof v === 'number' && Number.isFinite(v) ? v : null;
const axis = (v: number) => Math.round(Math.max(0, Math.min(1, v)) * 100) / 100;

export function galaxyPrefill(input: GalaxyProfile): GalaxyPrefill {
  if (!input || input.schema !== GALAXY_PROFILE_SCHEMA) fail('unsupported schema');
  const profile = normaliseGalaxyProfile(input.config);
  const config = profile.config;
  const genre = String(config.genre);
  const specialty = galaxyGenre(genre);
  const mapped = mappedBriefGenre(genre);
  const userVision = typeof config.game_vision === 'string' ? config.game_vision.trim() : '';
  const title = String(config.title).trim();
  const labels = [
    'Project title: ' + title + '.',
    specialty ? 'Specialized game genre: ' + specialty.name + '.' : 'Specialized genre ID: ' + genre + '.',
    typeof config.subgenre === 'string' && config.subgenre ? 'Subgenre: ' + config.subgenre + '.' : '',
    typeof config.game_tone === 'string' ? 'Tone: ' + config.game_tone + '.' : '',
    typeof config.visual_style === 'string' ? 'Visual style: ' + config.visual_style + '.' : '',
    typeof config.combat_style === 'string' ? 'Combat style: ' + config.combat_style + '.' : '',
  ].filter(Boolean).join('\n');
  const vision = userVision ? (userVision + '\n' + labels).slice(0, 4000) : labels.slice(0, 4000);
  const axes: Record<string, number> = {};
  const pace: Record<string, number> = {
    slow_burn: 0.2, standard: 0.5, action_packed: 0.8, breakneck: 1,
  };
  const difficulty: Record<string, number> = {
    gentle: 0.2, steady: 0.5, adaptive: 0.6, punishing: 0.95,
  };
  if (typeof config.game_pace === 'string' && Object.prototype.hasOwnProperty.call(pace, config.game_pace)) axes.tempo = pace[config.game_pace];
  if (typeof config.difficulty_curve === 'string' && Object.prototype.hasOwnProperty.call(difficulty, config.difficulty_curve)) axes.risk = difficulty[config.difficulty_curve];
  if (numeric(config.narrative_branching) !== null) axes.agency = axis(numeric(config.narrative_branching)! / 7);
  if (numeric(config.juice) !== null) axes.spectacle = axis(numeric(config.juice)! / 10);
  // No speculative remapping of gore, sound era, or dialog depth to other
  // tensor axes. Their real values are fully retained inside the profile.
  return { vision, genre: specialty ? genre : null, mappedGenre: mapped, axes, profile };
}

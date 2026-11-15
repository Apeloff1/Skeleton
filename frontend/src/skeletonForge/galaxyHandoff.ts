/**
 * Original Galaxy Studio -> GameForge handoff. Pure, bounded, versioned.
 *
 * One-use, same-runtime handoffs are deliberate: local app navigation is not
 * an account-authenticated project store. The complete authoring snapshot
 * is carried through the next GameForge run and emitted as a project artifact.
 */
import { galaxyGenre, mappedBriefGenre } from './galaxyGenres';
import { GENRE_CHOICES } from './genreCatalog';

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
const MAX_CANONICAL_BYTES = 600_000;

function charge(budget: { count: number; bytes: number }, bytes: number): void {
  budget.bytes += bytes;
  if (budget.bytes > MAX_CANONICAL_BYTES) fail('configuration exceeds canonical 600 KB');
}

function stringBytes(value: string): number {
  if (value.length > 12_000) fail('a text field exceeds its maximum length');
  let bytes = 2;
  for (let i = 0; i < value.length; i++) {
    const code = value.charCodeAt(i);
    if (code >= 0xd800 && code <= 0xdbff) {
      const next = value.charCodeAt(++i);
      if (!(next >= 0xdc00 && next <= 0xdfff)) fail('invalid Unicode text');
      bytes += 12;
    } else if (code >= 0xdc00 && code <= 0xdfff) {
      fail('invalid Unicode text');
    } else if (code >= 127 || code < 32) {
      // Conservative bound for Python ensure_ascii and JSON control escapes.
      bytes += 6;
    } else {
      bytes += code === 34 || code === 92 ? 2 : 1;
    }
  }
  return bytes;
}

function guard(value: unknown, budget: { count: number; bytes: number }, depth: number): unknown {
  if (++budget.count > MAX_FIELDS || depth > MAX_DEPTH) fail('configuration exceeds allowed complexity');
  if (value === null || typeof value === 'boolean') {
    charge(budget, value === false ? 5 : 4);
    return value;
  }
  if (typeof value === 'number') {
    if (!Number.isFinite(value) || Math.abs(value) > Number.MAX_SAFE_INTEGER) fail('non-finite or unsafe number');
    charge(budget, 32); // bounded conservative cross-runtime numeric representation
    return value;
  }
  if (typeof value === 'string') {
    charge(budget, stringBytes(value));
    return value;
  }
  if (Array.isArray(value)) {
    if (value.length > 4_096) fail('array exceeds limit');
    charge(budget, value.length + 2);
    const output: unknown[] = [];
    for (let i = 0; i < value.length; i++) {
      const entry = Object.getOwnPropertyDescriptor(value, String(i));
      if (!entry || !('value' in entry) || entry.value === undefined) fail('undefined or accessor array value');
      output.push(guard(entry.value, budget, depth + 1));
    }
    return output;
  }
  if (!plain(value)) fail('non-JSON data is forbidden');
  const keys = Object.keys(value);
  if (keys.length > 4_096) fail('object exceeds limit');
  charge(budget, keys.length * 2 + 2);
  const output: Record<string, unknown> = Object.create(null);
  for (const key of keys) {
    if (!/^[a-zA-Z][a-zA-Z0-9_.-]{0,127}$/.test(key) || ['__proto__', 'constructor', 'prototype'].includes(key)) {
      fail('invalid configuration key');
    }
    const entry = Object.getOwnPropertyDescriptor(value, key);
    if (!entry || !('value' in entry)) fail('configuration accessor is forbidden');
    if (entry.value !== undefined) {
      charge(budget, stringBytes(key));
      output[key] = guard(entry.value, budget, depth + 1);
    }
  }
  return output;
}

export function normaliseGalaxyProfile(payload: unknown): GalaxyProfile {
  // Apply the same envelope-depth and aggregate budget as the server
  // before reading semantic fields; retain only detached JSON-native data.
  payload = guard(payload, { count: 2, bytes: 128 }, 1);
  if (!plain(payload) || typeof payload.title !== 'string' || !payload.title.trim()
      || payload.title.length > 120 || typeof payload.genre !== 'string'
      || !payload.genre || payload.genre.length > 128) fail('missing game title or genre');
  for (const field of MATRIX_FIELDS) if (!plain(payload[field])) fail('missing ' + field);
  for (const field of [...MATRIX_FIELDS, 'narrative_phases']) {
    const phases = payload[field];
    if (!plain(phases) || Object.keys(phases).length > 512) fail('matrix phases exceed limit');
    for (const axes of Object.values(phases)) {
      if (!plain(axes) || Object.keys(axes).length > 128 ||
        Object.values(axes).some((v) => typeof v !== 'number' || !Number.isFinite(v) || v < 0 || v > 1000)) {
        fail('invalid matrix axis value');
      }
    }
  }
  if (!plain(payload.narrative_phases) || !plain(payload.extra_params) || !plain(payload.style_params)) {
    fail('missing narrative, extended or style controls');
  }
  if (Object.values(payload.extra_params as Record<string, unknown>).some(value => typeof value === 'boolean')) fail('numeric slider cannot be boolean');
  let serialized = '';
  try { serialized = JSON.stringify(payload); } catch { fail('non-serializable input'); }
  if (!serialized || serialized.length > MAX_PROFILE_CHARS) fail('configuration exceeds 450 KB');
  // Defensive clone protects the snapshot against both subsequent UI editing
  // and a caller mutating a returned value before its one-use consumption.
  return { schema: GALAXY_PROFILE_SCHEMA, config: JSON.parse(serialized) };
}

// The route URL is a *public hint*, not proof of account ownership. The
// originating and receiving app routes supply the same auth-epoch at both
// boundaries; an account switch invalidates even a still-live hint.
let pending: { id: string; value: GalaxyProfile; created: number; expires: number; ownerEpoch: number | null } | null = null;
let sequence = 0;

export function prepareGalaxyHandoff(
  payload: unknown, now: number = Date.now(), ownerEpoch: number | null = null,
): string {
  if (!Number.isSafeInteger(now) || now < 0 || now > Number.MAX_SAFE_INTEGER - PROFILE_TTL_MS) fail('invalid clock');
  if (ownerEpoch !== null && (!Number.isSafeInteger(ownerEpoch) || ownerEpoch < 0)) {
    fail('invalid owner epoch');
  }
  const value = normaliseGalaxyProfile(payload);
  // ID is only a routing hint. It is NOT an authorization token. Data lives
  // only in JS memory, never in localStorage/AsyncStorage or a public URL.
  const id = 'g' + now.toString(36) + 'x' + (++sequence).toString(36);
  pending = { id, value, created: now, expires: now + PROFILE_TTL_MS, ownerEpoch };
  return id;
}

export function consumeGalaxyHandoff(
  id: string | null | undefined, now: number = Date.now(), ownerEpoch: number | null = null,
): GalaxyProfile | null {
  if (!id || !pending || id !== pending.id) return null;
  const captured = pending;
  pending = null;
  if (!Number.isSafeInteger(now) || now < captured.created || now > captured.expires ||
      ownerEpoch !== captured.ownerEpoch) return null;
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
  const canonical = genre.toLowerCase().replace(/_/g, '-');
  const mapped = mappedBriefGenre(genre) ?? (GENRE_CHOICES.includes(canonical) ? canonical : null);
  // Direct profile import and the creator bridge must agree: do not retain
  // a previous project's genre vote for an incompatible selected genre.
  if (!mapped) fail('selected genre has no compatible GameForge mapping');
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

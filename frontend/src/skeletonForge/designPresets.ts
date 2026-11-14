/**
 * Explicit local-only GameForge design presets.
 *
 * Not a cloud project vault, authentication token or provider credential.
 * Saving is opt-in; the application never silently persists Galaxy transfers.
 * All replayed settings are independently validated and bounded before they
 * reach the source-generating GameForge request.
 */
import type { QuestionnaireState } from './questionnaire';
import { INITIAL_STATE, ARCHETYPES, BRIEF_FACETS, PLAYABLE_SLICES, TARGETS, VISION_MAX } from './questionnaire';
import { isDesignAxis, normaliseAxisEdit } from './instruments';
import { galaxyGenre } from './galaxyGenres';
import { GALAXY_PROFILE_SCHEMA, normaliseGalaxyProfile } from './galaxyHandoff';

export const DESIGN_PRESET_SCHEMA = 'skeleton.gameforge.design_presets.v1' as const;
export const DESIGN_PRESET_STORAGE_KEY = '@skeleton_gameforge_design_presets_v1';
export const MAX_SAVED_PRESETS = 24;
export const MAX_PRESET_CHARS = 475_000;
export const MAX_STORE_CHARS = 2_000_000;

export interface DesignPreset {
  schema: typeof DESIGN_PRESET_SCHEMA;
  name: string;
  updatedAt: number;
  state: QuestionnaireState;
}

function plain(value: unknown): value is Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return false;
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
}

function reject(reason: string): never {
  throw new Error('GameForge preset rejected: ' + reason);
}

function safeName(input: unknown): string {
  if (typeof input !== 'string') reject('preset name must be text');
  const name = input.trim();
  if (!name || name.length > 64 || /[\u0000-\u001f\u007f]/.test(name)) {
    reject('preset name must be 1–64 printable characters');
  }
  return name;
}

function safeOption(value: unknown, label: string): string | null {
  if (value === null) return null;
  if (typeof value !== 'string' || !/^[a-zA-Z0-9_.-]{1,96}$/.test(value)) {
    reject(label + ' identifier is invalid');
  }
  return value;
}

function answerMap(
  input: unknown, label: string, allowed: Record<string, readonly string[]> | null,
  maximum: number,
): Record<string, string> {
  if (!plain(input) || Object.keys(input).length > maximum) reject(label + ' is invalid');
  const result: Record<string, string> = Object.create(null);
  for (const [key, value] of Object.entries(input)) {
    if (!/^[a-z][a-z0-9_-]{0,63}$/.test(key) || key === 'constructor' || key === 'prototype') {
      reject(label + ' key is invalid');
    }
    if (typeof value !== 'string' || !/^[a-zA-Z0-9_.-]{1,96}$/.test(value)) {
      reject(label + ' answer is invalid');
    }
    if (allowed && (!allowed[key] || !allowed[key].includes(value))) {
      reject(label + ' answer is unsupported');
    }
    result[key] = value;
  }
  return result;
}

export function normalisePresetState(input: unknown): QuestionnaireState {
  if (!plain(input)) reject('missing questionnaire');
  if (typeof input.vision !== 'string' || input.vision.length > VISION_MAX) {
    reject('vision exceeds the maximum');
  }
  const permitted = Object.fromEntries(BRIEF_FACETS.map((facet) => [facet.id, facet.options]));
  const brief = answerMap(input.brief, 'creative brief', permitted, BRIEF_FACETS.length);
  // Live backend beat catalogs may add ids. Keep bounded original answers
  // rather than silently discarding their user-selected configuration.
  const beats = answerMap(input.beats, 'design beats', null, 64);
  if (!plain(input.instruments) || Object.keys(input.instruments).length > 10) {
    reject('invalid cockpit axis inventory');
  }
  const instruments: Record<string, number> = Object.create(null);
  for (const [axis, value] of Object.entries(input.instruments)) {
    if (!isDesignAxis(axis) || typeof value !== 'number') reject('unrecognised cockpit axis');
    const normalized = normaliseAxisEdit(value);
    if (normalized === null) reject('cockpit value must be finite and bounded');
    instruments[axis] = normalized;
  }
  const options = input.options;
  if (!plain(options)) reject('missing forge output choices');
  if (!ARCHETYPES.some((row) => row.id === options.archetype)
      || !TARGETS.some((row) => row.id === options.target)) {
    reject('unavailable archetype or output');
  }
  const era = safeOption(options.era, 'era');
  const generation = safeOption(options.generation, 'generation');
  const genre = input.galaxyGenre === null ? null : input.galaxyGenre;
  if (genre !== null && (typeof genre !== 'string' || !galaxyGenre(genre))) {
    reject('unknown historical genre');
  }
  let profile = null;
  if (input.galaxyProfile !== null) {
    if (!plain(input.galaxyProfile) || input.galaxyProfile.schema !== GALAXY_PROFILE_SCHEMA) {
      reject('invalid historical Galaxy profile');
    }
    profile = normaliseGalaxyProfile(input.galaxyProfile.config);
  }
  const quest = input.quest;
  const playable = input.playable;
  if (!plain(quest) || typeof quest.enabled !== 'boolean'
      || !Number.isInteger(quest.length) || (quest.length as number) < 1 || (quest.length as number) > 8) {
    reject('invalid native quest configuration');
  }
  if (!plain(playable) || typeof playable.enabled !== 'boolean'
      || typeof playable.launch !== 'boolean'
      || !PLAYABLE_SLICES.some((row) => row.id === playable.mode)) {
    reject('invalid playable mini-game selection');
  }
  if (quest.enabled && playable.launch) reject('quest and mini-game cannot both own startup');
  if (!playable.enabled && playable.launch) reject('disabled mini-game cannot own startup');
  return {
    ...INITIAL_STATE,
    step: 'options',
    vision: input.vision,
    brief, beats, instruments,
    galaxyGenre: genre as string | null,
    galaxyProfile: profile,
    quest: { enabled: quest.enabled, length: quest.length as number },
    playable: { enabled: playable.enabled, mode: playable.mode as string, launch: playable.launch },
    options: { archetype: options.archetype as string, target: options.target as string, era, generation },
  };
}

export function makeDesignPreset(name: string, state: QuestionnaireState, now: number = Date.now()): DesignPreset {
  if (!Number.isSafeInteger(now) || now < 0) reject('invalid update time');
  const preset: DesignPreset = {
    schema: DESIGN_PRESET_SCHEMA, name: safeName(name),
    updatedAt: now, state: normalisePresetState(state),
  };
  if (JSON.stringify(preset).length > MAX_PRESET_CHARS) reject('individual design is oversized');
  return preset;
}

function normalisePreset(input: unknown): DesignPreset {
  if (!plain(input) || input.schema !== DESIGN_PRESET_SCHEMA) reject('unsupported preset version');
  return makeDesignPreset(input.name as string, input.state as QuestionnaireState, input.updatedAt as number);
}

export function encodeDesignPresets(input: readonly DesignPreset[]): string {
  if (!Array.isArray(input) || input.length > MAX_SAVED_PRESETS) reject('too many saved designs');
  const seen = new Set<string>();
  const entries: DesignPreset[] = [];
  for (const candidate of input) {
    const record = normalisePreset(candidate);
    const key = record.name.toLocaleLowerCase('en');
    if (seen.has(key)) reject('duplicate design names');
    seen.add(key);
    entries.push(record);
  }
  const encoded = JSON.stringify({ schema: DESIGN_PRESET_SCHEMA, entries });
  if (encoded.length > MAX_STORE_CHARS) reject('local preset library capacity exceeded');
  return encoded;
}

export function decodeDesignPresets(raw: string | null): DesignPreset[] {
  if (raw === null) return [];
  if (typeof raw !== 'string' || raw.length > MAX_STORE_CHARS) reject('local library is malformed or oversized');
  let document: unknown;
  try { document = JSON.parse(raw); } catch { reject('local library JSON is damaged'); }
  if (!plain(document) || document.schema !== DESIGN_PRESET_SCHEMA || !Array.isArray(document.entries)) {
    reject('unsupported local library');
  }
  const entries = document.entries.map(normalisePreset);
  // Re-encode to validate aggregate budget, duplicate names and schema.
  encodeDesignPresets(entries);
  return entries;
}

export function saveDesignPreset(existing: readonly DesignPreset[], record: DesignPreset): DesignPreset[] {
  const validated = normalisePreset(record);
  const key = validated.name.toLocaleLowerCase('en');
  const rest = existing.filter((item) => item.name.toLocaleLowerCase('en') !== key);
  const result = [validated, ...rest];
  encodeDesignPresets(result);
  return result;
}

export function deleteDesignPreset(existing: readonly DesignPreset[], name: string): DesignPreset[] {
  const key = safeName(name).toLocaleLowerCase('en');
  const result = existing.filter((item) => item.name.toLocaleLowerCase('en') !== key);
  encodeDesignPresets(result);
  return result;
}

/** Explicit, bounded, local-only draft handoff between original Galaxy Studio and GameForge.
 * Only concepts both workspaces can represent cross the boundary. No build is started.
 * Legacy GameForge axes, quest option and answered beats are carried unmodified when
 * visiting Galaxy, and restored when returning. Galaxy matrices remain Galaxy-owned.
 */
import type { QuestionnaireState } from './questionnaire';
import { DESIGN_AXES } from './instruments';
import { GALAXY_CHOICES, mappedBriefGenre } from './galaxyGenres';
import { GENRE_CHOICES } from './genreCatalog';

export const CREATOR_BRIDGE_SCHEMA = 'skeleton.creator.handoff.v1' as const;
export const CREATOR_BRIDGE_TTL_MS = 20 * 60 * 1000;

export type CreatorBridgeTarget = 'galaxy' | 'forge';
export interface CreatorBridgeDraft {
  schema: typeof CREATOR_BRIDGE_SCHEMA;
  target: CreatorBridgeTarget;
  createdMs: number;
  vision: string;
  brief: Record<string, string>;
  beats: Record<string, string>;
  instruments: Record<string, number>;
  galaxyGenre: string | null;
  options: QuestionnaireState['options'];
  quest: { enabled: boolean; length: number };
}
export interface GalaxyBridgeSelection {
  title: string;
  vision: string;
  genreId: string | null;
}

const availableGenres = new Set(GENRE_CHOICES);
const galaxyIds = new Set(GALAXY_CHOICES.map((x) => x.id));
const axes = new Set<string>(DESIGN_AXES.map((x) => x.id));
const allowedBrief = new Set(['genre', 'theme', 'perspective', 'combat', 'progression']);
const allowedBeats = new Set([
  'pace', 'death', 'combat', 'info', 'loot', 'heat', 'author', 'social',
  'space', 'fail_state', 'ai', 'era_explicit',
]);
const validKey = /^[a-z][a-z0-9_-]{0,47}$/;
const validId = /^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}$/;

const record = (value: unknown): Record<string, unknown> | null =>
  value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null;
const cleanText = (value: unknown, length: number): string =>
  typeof value === 'string' ? value.slice(0, length) : '';

function cleanChoices(value: unknown, max: number, allowed: ReadonlySet<string>): Record<string, string> {
  const out: Record<string, string> = {};
  const source = record(value);
  if (!source) return out;
  let count = 0;
  for (const [key, choice] of Object.entries(source)) {
    if (count >= max) break;
    if (allowed.has(key) && validKey.test(key) &&
        typeof choice === 'string' && choice.length <= 80 && validId.test(choice)) {
      out[key] = choice;
      count++;
    }
  }
  return out;
}

export function parseCreatorBridge(
  raw: unknown,
  target: CreatorBridgeTarget,
  now: number = Date.now(),
): CreatorBridgeDraft | null {
  const input = record(raw);
  if (!input || input.schema !== CREATOR_BRIDGE_SCHEMA || input.target !== target ||
      typeof input.createdMs !== 'number' || !Number.isSafeInteger(input.createdMs) ||
      !Number.isFinite(now) || input.createdMs > now + 30_000 ||
      now - input.createdMs > CREATOR_BRIDGE_TTL_MS) return null;
  const vision = cleanText(input.vision, 4000);
  const brief = cleanChoices(input.brief, 5, allowedBrief);
  if (brief.genre && !availableGenres.has(brief.genre)) delete brief.genre;
  const beats = cleanChoices(input.beats, 12, allowedBeats);
  const instruments: Record<string, number> = {};
  const rawAxes = record(input.instruments);
  if (rawAxes) {
    for (const [key, value] of Object.entries(rawAxes)) {
      if (axes.has(key) && typeof value === 'number' &&
          Number.isFinite(value) && value >= 0 && value <= 1) instruments[key] = value;
    }
  }
  const genre = typeof input.galaxyGenre === 'string' && galaxyIds.has(input.galaxyGenre) ? input.galaxyGenre : null;
  const options = record(input.options) ?? {};
  const originalTarget = options.target === 'json' ? 'json' : 'godot';
  const archetype = typeof options.archetype === 'string' &&
    ['auto', 'vision', 'extraction', 'combat_loop', 'pipeline'].includes(options.archetype) ? options.archetype : 'auto';
  const era = typeof options.era === 'string' && validId.test(options.era) ? options.era : null;
  const generation = typeof options.generation === 'string' && validId.test(options.generation) ? options.generation : null;
  const rawQuest = record(input.quest);
  const length = rawQuest && Number.isInteger(rawQuest.length) &&
    (rawQuest.length as number) >= 1 && (rawQuest.length as number) <= 8 ? rawQuest.length as number : 3;
  return {
    schema: CREATOR_BRIDGE_SCHEMA, target, createdMs: input.createdMs,
    vision, brief, beats, instruments, galaxyGenre: genre,
    options: { archetype, target: originalTarget, era, generation },
    quest: { enabled: rawQuest?.enabled === true, length },
  };
}

export function handoffFromForge(state: QuestionnaireState, now: number = Date.now()): CreatorBridgeDraft {
  const raw = {
    schema: CREATOR_BRIDGE_SCHEMA, target: 'galaxy', createdMs: now,
    vision: state.vision, brief: state.brief, beats: state.beats,
    instruments: state.instruments, galaxyGenre: state.galaxyGenre,
    options: state.options, quest: state.quest,
  };
  const valid = parseCreatorBridge(raw, 'galaxy', now);
  if (!valid) throw new Error('Cannot prepare bounded creator handoff');
  return valid;
}

export function handoffFromGalaxy(
  selection: GalaxyBridgeSelection,
  prior: CreatorBridgeDraft | null = null,
  now: number = Date.now(),
): CreatorBridgeDraft {
  const previous = prior ? parseCreatorBridge(prior, 'galaxy', now) : null;
  const genre = selection.genreId && galaxyIds.has(selection.genreId) ? selection.genreId : previous?.galaxyGenre ?? null;
  const brief = { ...(previous?.brief ?? {}) };
  if (genre) {
    const mapped = mappedBriefGenre(genre);
    if (mapped && availableGenres.has(mapped)) brief.genre = mapped;
  }
  const vision = cleanText(selection.vision, 4000).trim() ||
    cleanText(selection.title, 160).trim() || previous?.vision || '';
  const raw = {
    schema: CREATOR_BRIDGE_SCHEMA, target: 'forge', createdMs: now,
    vision, brief, beats: previous?.beats ?? {}, instruments: previous?.instruments ?? {},
    galaxyGenre: genre, options: previous?.options ?? { archetype: 'auto', target: 'godot', era: null, generation: null },
    quest: previous?.quest ?? { enabled: false, length: 3 },
  };
  const valid = parseCreatorBridge(raw, 'forge', now);
  if (!valid) throw new Error('Cannot prepare bounded Galaxy handoff');
  return valid;
}

export function forgeStateFromHandoff(raw: CreatorBridgeDraft, now: number = Date.now()): QuestionnaireState | null {
  const draft = parseCreatorBridge(raw, 'forge', now);
  if (!draft) return null;
  return {
    step: 'brief', vision: draft.vision, brief: draft.brief, beats: draft.beats,
    instruments: draft.instruments, galaxyGenre: draft.galaxyGenre,
    options: draft.options, quest: draft.quest,
  };
}

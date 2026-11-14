/** Explicit, bounded, local-only draft handoff between original Galaxy Studio and GameForge.
 * Only concepts both workspaces can represent cross the boundary. No build is started.
 * Legacy GameForge axes, quest option and answered beats are carried unmodified when
 * visiting Galaxy, and restored when returning. Galaxy matrices remain Galaxy-owned.
 */
import { STEPS, reachable, type QuestionnaireState } from './questionnaire';
import { DESIGN_AXES } from './instruments';
import { GALAXY_CHOICES, mappedBriefGenre } from './galaxyGenres';
import { GENRE_CHOICES } from './genreCatalog';

export const CREATOR_BRIDGE_SCHEMA = 'skeleton.creator.handoff.v1' as const;
export const CREATOR_BRIDGE_TTL_MS = 20 * 60 * 1000;

export type CreatorBridgeTarget = 'galaxy' | 'forge' | 'studio';
export interface CreatorBridgeDraft {
  schema: typeof CREATOR_BRIDGE_SCHEMA;
  target: CreatorBridgeTarget;
  createdMs: number;
  /** Optional first-install Studio project origin, never a URL or account ID. */
  studioProjectId?: string | null;
  studioProjectUpdatedAt?: string | null;
  /** Retain the user's current place in the questionnaire. */
  step: QuestionnaireState['step'];
  vision: string;
  brief: Record<string, string>;
  beats: Record<string, string>;
  instruments: Record<string, number>;
  galaxyGenre: string | null;
  options: QuestionnaireState['options'];
  quest: { enabled: boolean; length: number };
  playable: { enabled: boolean };
  playtest: 'off' | 'auto' | 'require';
  sourceExport: { enabled: boolean };
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
  const step: QuestionnaireState['step'] =
    typeof input.step === 'string' && STEPS.includes(input.step as QuestionnaireState['step'])
      ? input.step as QuestionnaireState['step'] : 'brief';
  const studioProjectId = typeof input.studioProjectId === 'string'
    && validId.test(input.studioProjectId) ? input.studioProjectId : null;
  const studioProjectUpdatedAt = studioProjectId
    && typeof input.studioProjectUpdatedAt === 'string'
    && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(input.studioProjectUpdatedAt)
    && Number.isFinite(Date.parse(input.studioProjectUpdatedAt))
      ? input.studioProjectUpdatedAt : null;
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
  const playtest = input.playtest === 'auto' || input.playtest === 'require'
    ? input.playtest : 'off';
  const rawExport = record(input.sourceExport);
  const rawPlayable = record(input.playable);
  const rawQuest = record(input.quest);
  const length = rawQuest && Number.isInteger(rawQuest.length) &&
    (rawQuest.length as number) >= 1 && (rawQuest.length as number) <= 8 ? rawQuest.length as number : 3;
  return {
    schema: CREATOR_BRIDGE_SCHEMA, target, createdMs: input.createdMs,
    studioProjectId, studioProjectUpdatedAt,
    step, vision, brief, beats, instruments, galaxyGenre: genre,
    options: { archetype, target: originalTarget, era, generation },
    quest: { enabled: rawQuest?.enabled === true, length },
    playable: { enabled: rawPlayable?.enabled === true },
    playtest,
    sourceExport: { enabled: rawExport?.enabled === true },
  };
}

export function handoffFromForge(
  state: QuestionnaireState, now: number = Date.now(),
  origin: CreatorBridgeDraft | null = null,
): CreatorBridgeDraft {
  // Accept session metadata only from a previously verified Forge handoff.
  // Older v1 drafts without optional Studio fields continue to parse.
  const admittedOrigin = origin ? parseCreatorBridge(origin, 'forge', origin.createdMs) : null;
  const raw = {
    schema: CREATOR_BRIDGE_SCHEMA, target: 'galaxy', createdMs: now,
    studioProjectId: admittedOrigin?.studioProjectId ?? null,
    studioProjectUpdatedAt: admittedOrigin?.studioProjectUpdatedAt ?? null,
    step: state.step, vision: state.vision, brief: state.brief, beats: state.beats,
    instruments: state.instruments, galaxyGenre: state.galaxyGenre,
    options: state.options, quest: state.quest,
    playable: state.playable, playtest: state.playtest,
    sourceExport: state.sourceExport,
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
  // The receiving route already validated and consumed this short-lived handoff
  // before opening the Galaxy editor. Once accepted into that route's memory,
  // an editing session must not erase the user's authored Forge knobs or quest
  // merely because they spent more than 20 minutes tuning Galaxy matrices.
  // Revalidate shape against the original accepted timestamp; the *new*
  // outbound handoff receives today's timestamp and its own short TTL.
  const previous = prior ? parseCreatorBridge(prior, 'galaxy', prior.createdMs) : null;
  const selectedId = typeof selection.genreId === 'string' ? selection.genreId.trim() : null;
  const knownSpecialty = selectedId !== null && galaxyIds.has(selectedId);
  // A backend-fetched Galaxy genre may not yet be in its offline fallback.
  // Preserve one if it exactly corresponds to an authorized 158-choice
  // GameForge token; never silently discard an unrecognized selection.
  const canonicalToken = selectedId?.toLowerCase().replace(/_/g, '-') ?? null;
  if (selectedId && !knownSpecialty && (!canonicalToken || !availableGenres.has(canonicalToken))) {
    throw new Error('Selected Galaxy genre has no compatible GameForge mapping');
  }
  const genre = knownSpecialty ? selectedId : selectedId ? null : previous?.galaxyGenre ?? null;
  const brief = { ...(previous?.brief ?? {}) };
  if (knownSpecialty && selectedId) {
    const mapped = mappedBriefGenre(selectedId);
    if (!mapped || !availableGenres.has(mapped)) {
      throw new Error('Galaxy specialization mapping is incomplete');
    }
    brief.genre = mapped;
  } else if (canonicalToken && availableGenres.has(canonicalToken)) {
    brief.genre = canonicalToken;
  }
  const vision = cleanText(selection.vision, 4000).trim() ||
    cleanText(selection.title, 160).trim() || previous?.vision || '';
  const raw = {
    schema: CREATOR_BRIDGE_SCHEMA, target: 'forge', createdMs: now,
    studioProjectId: previous?.studioProjectId ?? null,
    studioProjectUpdatedAt: previous?.studioProjectUpdatedAt ?? null,
    step: previous?.step ?? 'brief', vision, brief, beats: previous?.beats ?? {}, instruments: previous?.instruments ?? {},
    galaxyGenre: genre, options: previous?.options ?? { archetype: 'auto', target: 'godot', era: null, generation: null },
    quest: previous?.quest ?? { enabled: false, length: 3 },
    playable: previous?.playable ?? { enabled: false },
    playtest: previous?.playtest ?? 'off',
    sourceExport: previous?.sourceExport ?? { enabled: false },
  };
  const valid = parseCreatorBridge(raw, 'forge', now);
  if (!valid) throw new Error('Cannot prepare bounded Galaxy handoff');
  return valid;
}

export function forgeStateFromHandoff(raw: CreatorBridgeDraft, now: number = Date.now()): QuestionnaireState | null {
  const draft = parseCreatorBridge(raw, 'forge', now);
  if (!draft) return null;
  const restored: QuestionnaireState = {
    step: draft.step, vision: draft.vision, brief: draft.brief, beats: draft.beats,
    instruments: draft.instruments, galaxyGenre: draft.galaxyGenre,
    options: draft.options, quest: draft.quest,
    playable: draft.playable,
    playtest: draft.playtest,
    sourceExport: draft.sourceExport,
  };
  // A valid handoff must not become a way to jump past a blocked vision
  // step. Preserve completed progress; reset only an unreachable step.
  return reachable(restored, restored.step) ? restored : { ...restored, step: 'vision' };
}


/** One-time, account-scoped import of an existing first-install project into
 * the advanced Forge cockpit. Nothing is re-generated or uploaded. */
export function handoffFromStudio(
  state: QuestionnaireState, projectId: string, updatedAt: string,
  now: number = Date.now(),
): CreatorBridgeDraft {
  const raw = handoffFromForge(state, now);
  const accepted = parseCreatorBridge({
    ...raw, target: 'forge',
    studioProjectId: projectId, studioProjectUpdatedAt: updatedAt,
  }, 'forge', now);
  if (!accepted || !accepted.studioProjectId || !accepted.studioProjectUpdatedAt) {
    throw new Error('Unrecognized source Studio project identity or revision');
  }
  return accepted;
}

/** Explicit return from the advanced cockpit into its original Studio project.
 * Preserves origin across arbitrarily long editing after acceptance, but
 * stamps a fresh short-lived transport envelope. */
export function handoffToStudio(
  state: QuestionnaireState, origin: CreatorBridgeDraft,
  now: number = Date.now(),
): CreatorBridgeDraft {
  const admitted = parseCreatorBridge(origin, 'forge', origin.createdMs);
  if (!admitted?.studioProjectId || !admitted.studioProjectUpdatedAt) {
    throw new Error('This Forge editor was not opened from a Studio project');
  }
  const outbound = handoffFromForge(state, now, admitted);
  const accepted = parseCreatorBridge({ ...outbound, target: 'studio' }, 'studio', now);
  if (!accepted || !accepted.studioProjectId || !accepted.studioProjectUpdatedAt) {
    throw new Error('Could not prepare Studio return without source custody');
  }
  return accepted;
}

/** The receiving first-install Studio only accepts a source-bound return. */
export function studioStateFromHandoff(
  raw: CreatorBridgeDraft, now: number = Date.now(),
): QuestionnaireState | null {
  const draft = parseCreatorBridge(raw, 'studio', now);
  if (!draft?.studioProjectId || !draft.studioProjectUpdatedAt) return null;
  return forgeStateFromHandoff({ ...draft, target: 'forge' }, now);
}

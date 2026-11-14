/**
 * Guided GameForge questionnaire — a pure reducer the cockpit screen drives.
 *
 * Steps: vision → brief (five creative-brief facets) → beats (twelve design
 * beats from GET /api/skeleton/beats) → forge options → review. The result
 * is a `RunRequest` for POST /api/skeleton/run. Beat answers are
 * authoritative server-side; brief facets only vote an era when no beat is
 * answered (skeleton/context/questionnaire.intake), and the UI says so.
 */
import type { Beat, RunRequest } from './types';
import { GENRE_CHOICES } from './genreCatalog';
import { isDesignAxis, normaliseAxisEdit, sparseInstrumentPayload } from './instruments';
import { mappedBriefGenre, specializedVision } from './galaxyGenres';
import { galaxyPrefill, type GalaxyProfile } from './galaxyHandoff';

export const STEPS = ['vision', 'brief', 'beats', 'options', 'review'] as const;
export type Step = typeof STEPS[number];

export const STEP_LABELS: Record<Step, string> = {
  vision: 'Vision',
  brief: 'Creative brief',
  beats: 'Design beats',
  options: 'Forge options',
  review: 'Review & forge',
};

/** Mirrors BRIEF_FACETS / the most common BRIEF_ERA_VOTES keys. */
export const BRIEF_FACETS: readonly { id: string; prompt: string; options: string[] }[] = [
  { id: 'genre', prompt: 'What kind of game is it?', options: GENRE_CHOICES },
  { id: 'theme', prompt: 'Where is it set?', options: ['sci-fi', 'fantasy', 'dark-fantasy', 'modern', 'post-apocalyptic', 'cyberpunk', 'horror', 'cozy', 'retro', 'historical', 'anime', 'noir'] },
  { id: 'perspective', prompt: 'How do we see it?', options: ['first-person', 'third-person', 'top-down', 'isometric', 'side-scrolling'] },
  { id: 'combat', prompt: 'How does it fight?', options: ['tactical', 'real-time', 'turn-based', 'melee', 'fast', 'stealth', 'card-based', 'puzzle-based', 'none'] },
  { id: 'progression', prompt: 'How does the player grow?', options: ['skill-tree', 'level-based', 'equipment', 'narrative', 'open-ended', 'permadeath', 'metroidvania', 'score'] },
];

/** Offline fallback for GET /api/skeleton/beats (same ids/options as BEATS). */
export const FALLBACK_BEATS: Beat[] = [
  { id: 'pace', prompt: 'How does time feel?', options: ['processional', 'frantic', 'cabinet', 'unhurried'] },
  { id: 'death', prompt: 'What does failure cost?', options: ['everything', 'the_raid', 'a_credit', 'nothing'] },
  { id: 'combat', prompt: 'How should a trash mob die?', options: ['earned', 'instantly', 'scarcely', 'politely'] },
  { id: 'info', prompt: 'How much does the world explain itself?', options: ['nothing', 'tactical', 'cinematic', 'footnotes'] },
  { id: 'loot', prompt: 'Is stuff a prize or a liability?', options: ['liability', 'build', 'score', 'gift'] },
  { id: 'heat', prompt: 'Does the gun fight the shooter?', options: ['yes', 'stamina', 'no', 'never'] },
  { id: 'author', prompt: 'Whose taste is this?', options: ['mine', 'the_studio', 'the_cabinet', 'the_dark'] },
  { id: 'social', prompt: 'Alone or extracted together?', options: ['solo', 'squad', 'leaderboard', 'kitchen'] },
  { id: 'space', prompt: 'What is the room?', options: ['arena', 'dungeon', 'facility', 'garden'] },
  { id: 'fail_state', prompt: 'How does a run end badly?', options: ['collapse', 'bonfire', 'game_over', 'it_doesnt'] },
  { id: 'ai', prompt: 'What should Jeeves be?', options: ['tactical', 'silent', 'hype', 'kind'] },
  { id: 'era_explicit', prompt: 'If you already know the dialect?', options: ['extraction_now', 'soulslike', 'boomer_shooter', 'unspecified'] },
];

export const ARCHETYPES: readonly { id: string; label: string; hint: string }[] = [
  { id: 'auto', label: 'Compose from vision', hint: 'Systems are chosen from the words in your vision (recommended).' },
  { id: 'extraction', label: 'Extraction preset', hint: 'The canonical heat / forge / collapse / extract loop.' },
  { id: 'combat_loop', label: 'Combat loop preset', hint: 'A tight fight-and-reward loop.' },
  { id: 'pipeline', label: 'Pipeline preset', hint: 'A linear production pipeline blueprint.' },
];

export const TARGETS: readonly { id: string; label: string }[] = [
  { id: 'godot', label: 'Godot 4 project' },
  { id: 'json', label: 'JSON blueprint' },
];

export const VISION_MAX = 4000;

export interface ForgeOptions {
  archetype: string;
  target: string;
  era: string | null;
  generation: string | null;
}

export const PLAYABLE_SLICES = [
  { id: 'extraction', label: 'Extraction', hint: 'Recover three caches while managing heat and reach exit' },
  { id: 'combat_loop', label: 'Arena Combat', hint: 'Survive and clear three escalating enemy waves' },
  { id: 'pipeline', label: 'Factory Logistics', hint: 'Carry raw materials through refinery and delivery' },
  { id: 'puzzle', label: 'Spatial Puzzle', hint: 'Activate switches in order to complete a room puzzle' },
  { id: 'racing', label: 'Racing Time Trial', hint: 'Complete three laps through a checkpoint course' },
  { id: 'survival', label: 'Scavenging Survival', hint: 'Manage hydration, collect supplies, reach shelter' },
  { id: 'stealth', label: 'Stealth Infiltration', hint: 'Avoid guard vision, retrieve intel and escape' },
  { id: 'crafting', label: 'Crafting Delivery', hint: 'Collect parts, use a workshop, deliver a crafted item' },
] as const;

/** Honest, implemented native effects only. All other axes stay in the
 * canonical tensor; the source receipt identifies remaining unmapped edits.
 */
export const PLAYABLE_TUNING_EFFECTS: Record<string, readonly string[]> = {
  extraction: ['Tempo → movement speed', 'Risk → heat pressure'],
  combat_loop: ['Tempo → movement speed', 'Lethality → starting health', 'Progression depth → combat waves'],
  pipeline: ['Tempo → movement speed', 'Progression depth → shipment quota'],
  puzzle: ['Tempo → movement speed', 'Mystery → switch hints'],
  racing: ['Tempo → movement speed', 'Risk → checkpoint time limit', 'Progression depth → race laps'],
  survival: ['Tempo → movement speed', 'Scarcity → hydration drain'],
  stealth: ['Tempo → movement speed', 'Risk → guard detection radius', 'Mystery → guard-zone visibility'],
  crafting: ['Tempo → movement speed'],
};

export interface QuestionnaireState {
  step: Step;
  vision: string;
  brief: Record<string, string>;
  beats: Record<string, string>;
  /** Explicit overrides only; an absent axis remains driven by the forge. */
  instruments: Record<string, number>;
  /** Historical Galaxy Studio genre specialization (mapped to a canonical vote). */
  galaxyGenre?: string | null;
  /** All 14 matrices, narrative, extras, classic sliders, style and production inputs. */
  galaxyProfile?: GalaxyProfile | null;
  /** Opt-in native generated-room quest. */
  quest?: { enabled: boolean; length: number };
  /** Native source-backed standalone mini-game, independent of blueprint archetype. */
  playable?: { enabled: boolean; mode: string; launch: boolean };
  /** Native execution off by default; opt-in with separate sidecar qualification. */
  playtest?: 'off' | 'auto' | 'require';
  /** User must explicitly opt in before any complete source bodies reach UI. */
  sourceExport?: { enabled: boolean };
  options: ForgeOptions;
}

export type QuestionnaireAction =
  | { type: 'setVision'; vision: string }
  | { type: 'setBrief'; facet: string; value: string | null }
  | { type: 'setBeat'; beat: string; value: string | null }
  | { type: 'setAxis'; axis: string; value: number | null }
  | { type: 'resetAxes' }
  | { type: 'setGalaxyGenre'; genre: string | null }
  | { type: 'importGalaxy'; profile: GalaxyProfile }
  | { type: 'clearGalaxyProfile' }
  | { type: 'restoreDesignPreset'; state: QuestionnaireState }
  | { type: 'setQuestEnabled'; value: boolean }
  | { type: 'setQuestLength'; value: number }
  | { type: 'setPlayableEnabled'; value: boolean }
  | { type: 'setPlayableMode'; value: string }
  | { type: 'setPlayableMainScene'; value: boolean }
  | { type: 'setPlaytestMode'; value: 'off' | 'auto' | 'require' }
  | { type: 'setSourceExportEnabled'; value: boolean }
  | { type: 'setOption'; key: keyof ForgeOptions; value: string | null }
  | { type: 'next' }
  | { type: 'back' }
  | { type: 'goto'; step: Step }
  | { type: 'reset' };

export const INITIAL_STATE: QuestionnaireState = {
  step: 'vision',
  vision: '',
  brief: {},
  beats: {},
  instruments: {},
  galaxyGenre: null,
  galaxyProfile: null,
  quest: { enabled: false, length: 3 },
  playable: { enabled: false, mode: 'extraction', launch: false },
  playtest: 'off',
  sourceExport: { enabled: false },
  options: { archetype: 'auto', target: 'godot', era: null, generation: null },
};

function toggle(map: Record<string, string>, key: string, value: string | null): Record<string, string> {
  const next = { ...map };
  if (value === null || next[key] === value) delete next[key];
  else next[key] = value;
  return next;
}

export function stepIndex(step: Step): number {
  return STEPS.indexOf(step);
}

/** Why the user cannot advance from `step` (null when they can). */
export function blockReason(state: QuestionnaireState, step: Step = state.step): string | null {
  if (step === 'vision' && !state.vision.trim() && !Object.keys(state.brief).length && !Object.keys(state.beats).length) {
    return 'Describe your game in a sentence or two (or skip ahead and answer the brief).';
  }
  if (step === 'vision' && state.vision.length > VISION_MAX) return `Keep the vision under ${VISION_MAX} characters.`;
  return null;
}

/** Steps reachable by direct navigation (every earlier step unblocked). */
export function reachable(state: QuestionnaireState, step: Step): boolean {
  const target = stepIndex(step);
  for (let i = 0; i < target; i += 1) {
    if (STEPS[i] === 'vision' && blockReason(state, 'vision')) {
      // The vision may be skipped once a brief facet or beat is chosen.
      return false;
    }
  }
  return true;
}

export function questionnaireReducer(state: QuestionnaireState, action: QuestionnaireAction): QuestionnaireState {
  switch (action.type) {
    case 'setVision':
      return { ...state, vision: String(action.vision ?? '').slice(0, VISION_MAX + 200) };
    case 'setBrief':
      return { ...state, brief: toggle(state.brief, action.facet, action.value),
        galaxyGenre: action.facet === 'genre' ? null : state.galaxyGenre,
        galaxyProfile: action.facet === 'genre' ? null : state.galaxyProfile };
    case 'setBeat':
      return { ...state, beats: toggle(state.beats, action.beat, action.value) };
    case 'setAxis': {
      if (!isDesignAxis(action.axis)) return state;
      const instruments = { ...(state.instruments || {}) };
      if (action.value === null) delete instruments[action.axis];
      else {
        const value = normaliseAxisEdit(action.value);
        if (value === null) return state;
        instruments[action.axis] = value;
      }
      return { ...state, instruments };
    }
    case 'resetAxes':
      return { ...state, instruments: {} };
    case 'importGalaxy': {
      const imported = galaxyPrefill(action.profile);
      return {
        ...state, vision: imported.vision, step: 'options',
        brief: { ...state.brief, ...(imported.mappedGenre ? { genre: imported.mappedGenre } : {}) },
        galaxyGenre: imported.genre, galaxyProfile: imported.profile,
        instruments: { ...state.instruments, ...imported.axes },
      };
    }
    case 'clearGalaxyProfile':
      return { ...state, galaxyProfile: null };
    case 'setGalaxyGenre': {
      const mapped = mappedBriefGenre(action.genre);
      if (action.genre && !mapped) return state;
      const brief = { ...state.brief };
      if (!action.genre || action.genre === state.galaxyGenre) {
        if (state.galaxyGenre && brief.genre === mappedBriefGenre(state.galaxyGenre)) delete brief.genre;
        return { ...state, brief, galaxyGenre: null, galaxyProfile: null };
      }
      brief.genre = mapped!;
      return { ...state, brief, galaxyGenre: action.genre, galaxyProfile: null };
    }
    case 'setQuestEnabled':
      return {
        ...state,
        quest: { ...INITIAL_STATE.quest!, ...state.quest, enabled: action.value === true },
        playable: action.value ? { ...INITIAL_STATE.playable!, ...state.playable, launch: false } : state.playable,
      };
    case 'setQuestLength': {
      if (!Number.isInteger(action.value) || action.value < 1 || action.value > 8) return state;
      return { ...state, quest: { ...INITIAL_STATE.quest!, ...state.quest, length: action.value } };
    }
    case 'setPlayableEnabled': {
      const enabled = action.value === true;
      return { ...state, playable: {
        ...INITIAL_STATE.playable!, ...state.playable, enabled,
        launch: enabled ? !!state.playable?.launch : false,
      } };
    }
    case 'setPlayableMode': {
      if (!PLAYABLE_SLICES.some((item) => item.id === action.value)) return state;
      return { ...state, playable: { ...INITIAL_STATE.playable!, ...state.playable, mode: action.value } };
    }
    case 'setPlayableMainScene': {
      if (action.value && (state.quest?.enabled || state.options.target !== 'godot')) return state;
      return { ...state, playable: {
        ...INITIAL_STATE.playable!, ...state.playable,
        launch: action.value === true && !!state.playable?.enabled,
      } };
    }
    case 'setPlaytestMode':
      if (action.value !== 'off' && state.options.target !== 'godot') return state;
      return { ...state, playtest: action.value };
    case 'setSourceExportEnabled':
      return { ...state, sourceExport: { enabled: action.value === true } };
    case 'setOption': {
      const value = action.value === '' ? null : action.value;
      if (action.key === 'archetype' || action.key === 'target') {
        return { ...state, options: { ...state.options, [action.key]: value ?? INITIAL_STATE.options[action.key] } };
      }
      return { ...state, options: { ...state.options, [action.key]: value } };
    }
    case 'next': {
      if (blockReason(state)) return state;
      const i = stepIndex(state.step);
      return i < STEPS.length - 1 ? { ...state, step: STEPS[i + 1] } : state;
    }
    case 'back': {
      const i = stepIndex(state.step);
      return i > 0 ? { ...state, step: STEPS[i - 1] } : state;
    }
    case 'goto':
      return reachable(state, action.step) ? { ...state, step: action.step } : state;
    case 'restoreDesignPreset':
      return { ...action.state, step: 'options' };
    case 'reset':
      return INITIAL_STATE;
    default:
      return state;
  }
}

export interface Progress {
  answered: number;
  total: number;
  ratio: number;
  beatsAnswered: number;
  briefAnswered: number;
}

export function progress(state: QuestionnaireState, beats: Beat[] = FALLBACK_BEATS): Progress {
  const beatsAnswered = beats.filter((b) => state.beats[b.id]).length;
  const briefAnswered = BRIEF_FACETS.filter((f) => state.brief[f.id]).length;
  const total = 1 + BRIEF_FACETS.length + beats.length;
  const answered = (state.vision.trim() ? 1 : 0) + briefAnswered + beatsAnswered;
  return { answered, total, ratio: total ? answered / total : 0, beatsAnswered, briefAnswered };
}

/** Which input will decide the era server-side, for an honest review note. */
export function eraSource(state: QuestionnaireState): 'override' | 'beats' | 'brief' | 'vision' {
  if (state.options.era) return 'override';
  if (Object.keys(state.beats).length) return 'beats';
  if (Object.keys(state.brief).length) return 'brief';
  return 'vision';
}

export const ERA_SOURCE_COPY: Record<ReturnType<typeof eraSource>, string> = {
  override: 'Era is pinned explicitly in Forge options.',
  beats: 'Era is voted by your design beats (they outrank the brief).',
  brief: 'Era is voted by your creative brief.',
  vision: 'Era is detected from the words in your vision.',
};

export function buildRunRequest(state: QuestionnaireState): RunRequest {
  const answers: Record<string, string> = {};
  // Beat ids and brief facets share one namespace server-side ("combat"
  // exists in both); a beat answer wins because beats are authoritative.
  for (const [k, v] of Object.entries(state.brief)) answers[k] = v;
  for (const [k, v] of Object.entries(state.beats)) answers[k] = v;
  const request: RunRequest = {
    vision: state.galaxyProfile ? state.vision.trim().slice(0, VISION_MAX) : specializedVision(state.vision, state.galaxyGenre, VISION_MAX),
    era: state.options.era,
    archetype: state.options.archetype || 'auto',
    target: state.options.target || 'godot',
    generation: state.options.generation,
    answers,
  };
  const instrumentAxes = sparseInstrumentPayload(state.instruments);
  if (Object.keys(instrumentAxes).length) request.operator_axes = instrumentAxes;
  if (state.galaxyProfile) request.galaxy_profile = state.galaxyProfile;
  if (request.target === 'godot' && (state.playtest === 'auto' || state.playtest === 'require')) {
    request.playtest = state.playtest;
  }
  // An exact-run project export is opt-in and never causes a second forge.
  if (request.target === 'godot' && state.sourceExport?.enabled === true) {
    request.include_files = true;
  }
  if (state.playable?.enabled && request.target === 'godot') {
    const chosen = PLAYABLE_SLICES.find((slice) => slice.id === state.playable?.mode);
    if (chosen) {
      request.playable_content = true;
      request.playable_archetype = chosen.id;
      request.playable_main_scene = !!state.playable.launch && !state.quest?.enabled;
    }
  }
  if (state.quest?.enabled && request.target === 'godot') {
    request.quest_content = true;
    request.quest_length = Number.isInteger(state.quest.length) && state.quest.length >= 1 && state.quest.length <= 8 ? state.quest.length : 3;
  }
  return request;
}

/** Collisions where a beat answer shadows a brief facet of the same id. */
export function shadowedBriefFacets(state: QuestionnaireState): string[] {
  return Object.keys(state.brief).filter((k) => k in state.beats);
}

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
  { id: 'genre', prompt: 'What kind of game is it?', options: ['action-adventure', 'rpg', 'shooter', 'roguelike', 'survival', 'extraction', 'soulslike', 'strategy', 'tactics', 'metroidvania', 'horror', 'stealth', 'cozy', 'arcade', 'deckbuilder', 'puzzle'] },
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

export interface QuestionnaireState {
  step: Step;
  vision: string;
  brief: Record<string, string>;
  beats: Record<string, string>;
  options: ForgeOptions;
}

export type QuestionnaireAction =
  | { type: 'setVision'; vision: string }
  | { type: 'setBrief'; facet: string; value: string | null }
  | { type: 'setBeat'; beat: string; value: string | null }
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
      return { ...state, brief: toggle(state.brief, action.facet, action.value) };
    case 'setBeat':
      return { ...state, beats: toggle(state.beats, action.beat, action.value) };
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
  return {
    vision: state.vision.trim().slice(0, VISION_MAX),
    era: state.options.era,
    archetype: state.options.archetype || 'auto',
    target: state.options.target || 'godot',
    generation: state.options.generation,
    answers,
  };
}

/** Collisions where a beat answer shadows a brief facet of the same id. */
export function shadowedBriefFacets(state: QuestionnaireState): string[] {
  return Object.keys(state.brief).filter((k) => k in state.beats);
}

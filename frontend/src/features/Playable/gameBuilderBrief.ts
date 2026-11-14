/** Reviewed creator input for the existing playable generator, never execution evidence. */
export type GameBuilderGenre = 'shooter' | 'platformer' | 'roguelike';
export type GameBuilderDifficulty = 'relaxed' | 'balanced' | 'demanding';
export type BriefApplyMode = 'append' | 'replace';

export interface GameBuilderBriefDraft {
  genre: GameBuilderGenre;
  coreLoop: string;
  difficulty: GameBuilderDifficulty;
  theme: string;
  objective: string;
  constraints: string;
}

export interface GameBuilderStarter {
  id: GameBuilderGenre;
  title: string;
  subtitle: string;
  symbol: string;
  color: string;
  theme: string;
  objective: string;
  loops: readonly { id: string; title: string; description: string }[];
  acceptance: readonly string[];
}

export const GAME_BUILDER_STARTERS: readonly GameBuilderStarter[] = [
  {
    id: 'shooter', title: 'Neon frontier', subtitle: 'A compact arena shooter', symbol: '◎', color: '#A5D5F8',
    theme: 'A luminous salvage station at the edge of a violet nebula.',
    objective: 'Clear three escalating waves, defeat the final sentinel, and reach the extraction beacon.',
    loops: [
      { id: 'waves', title: 'Dodge → shoot → upgrade', description: 'Dodge readable enemy attacks, clear a wave, choose one upgrade, then face the next wave.' },
      { id: 'salvage', title: 'Explore → collect → extract', description: 'Explore a small arena, collect salvage under pressure, and return to an extraction zone.' },
    ],
    acceptance: ['Move and aim with visible controls; test the equivalent touch controls.', 'Clear a wave and verify its reward changes the next encounter.', 'Reach the final objective, then lose a second run and restart cleanly.'],
  },
  {
    id: 'platformer', title: 'Moonlit ascent', subtitle: 'A tactile little platformer', symbol: '↟', color: '#C5BAFF',
    theme: 'Moonlit rooftops, drifting lanterns, and a sleeping city below.',
    objective: 'Cross one complete handcrafted-feeling level, collect three lantern fragments, and light the summit beacon.',
    loops: [
      { id: 'precision', title: 'Read → jump → discover', description: 'Read a short obstacle sequence, jump through it, collect a discovery, and reach a safe checkpoint.' },
      { id: 'momentum', title: 'Run → leap → chain', description: 'Build momentum, chain forgiving jumps, and choose between a safe route and a rewarding shortcut.' },
    ],
    acceptance: ['Reach the first checkpoint using keyboard and touch controls.', 'Miss a jump and verify a fair, understandable checkpoint recovery.', 'Collect the required items, reach the goal, and restart without stale state.'],
  },
  {
    id: 'roguelike', title: 'Ember archive', subtitle: 'A small dungeon expedition', symbol: '◇', color: '#E8C596',
    theme: 'An ember-lit underground archive whose rooms rearrange after each expedition.',
    objective: 'Explore five connected rooms, earn a useful upgrade, recover the archive key, and escape.',
    loops: [
      { id: 'rooms', title: 'Explore → battle → choose', description: 'Explore a connected room, resolve a readable encounter, choose a meaningful reward, and advance.' },
      { id: 'risk', title: 'Prepare → risk → return', description: 'Manage a small health and supply budget, choose optional dangerous rooms, and return with the key.' },
    ],
    acceptance: ['Enter a room and complete an encounter with understandable feedback.', 'Choose an upgrade and verify it changes an actual player action or resource.', 'Escape with the objective; start another run with correctly reset inventory.'],
  },
];

export const GAME_BUILDER_DIFFICULTIES: readonly { id: GameBuilderDifficulty; title: string; description: string }[] = [
  { id: 'relaxed', title: 'Relaxed', description: 'Forgiving timing, readable attacks, generous recovery, and an accessible first success.' },
  { id: 'balanced', title: 'Balanced', description: 'Teach the controls safely, then increase challenge steadily with fair recovery.' },
  { id: 'demanding', title: 'Demanding', description: 'Precise decisions and escalating pressure, with clear telegraphs and immediate retries.' },
];

export const MAX_GAME_BUILDER_BRIEF_CHARS = 6000;
export const GAME_BUILDER_FIELD_LIMITS = { theme: 160, objective: 300, constraints: 600 } as const;

export class GameBuilderBriefError extends Error {
  constructor(public readonly code: 'invalid_draft' | 'draft_changed' | 'replace_unapproved' | 'brief_too_long', message: string) {
    super(message); this.name = 'GameBuilderBriefError';
  }
}

function text(value: unknown, label: string, maximum: number, optional = false, multiline = false): string {
  if (typeof value !== 'string' || Array.from(value).length > maximum ||
      /[\u0000-\u0008\u000b-\u001f\u007f\ud800-\udfff]/u.test(value) ||
      (!multiline && /[\r\n\u2028\u2029]/u.test(value))) {
    throw new GameBuilderBriefError('invalid_draft', `${label} must be ${multiline ? 'text' : 'a single line'} of up to ${maximum} characters.`);
  }
  const trimmed = value.trim();
  if (!optional && !trimmed) throw new GameBuilderBriefError('invalid_draft', `${label} is required.`);
  return trimmed;
}

export function gameBuilderStarter(genre: GameBuilderGenre): GameBuilderStarter {
  const selected = GAME_BUILDER_STARTERS.find(item => item.id === genre);
  if (!selected) throw new GameBuilderBriefError('invalid_draft', 'Choose a supported game starter.');
  return selected;
}

export function newGameBuilderDraft(genre: GameBuilderGenre = 'platformer'): GameBuilderBriefDraft {
  const starter = gameBuilderStarter(genre);
  return { genre, coreLoop: starter.loops[0].id, difficulty: 'balanced', theme: starter.theme,
    objective: starter.objective, constraints: '' };
}

/** Changing genre preserves creator edits; only untouched example text follows the starter. */
export function changeGameBuilderStarter(draft: GameBuilderBriefDraft, genre: GameBuilderGenre): GameBuilderBriefDraft {
  const before = gameBuilderStarter(draft.genre); const after = gameBuilderStarter(genre);
  return { ...draft, genre, coreLoop: after.loops[0].id,
    theme: draft.theme === before.theme ? after.theme : draft.theme,
    objective: draft.objective === before.objective ? after.objective : draft.objective };
}

export interface ReviewedGameBuilderBrief {
  readonly schema: 'skeleton.playable.reviewed-brief.v1';
  readonly previousBrief: string;
  readonly text: string;
  readonly genre: GameBuilderGenre;
  readonly requirements: readonly string[];
  readonly acceptance: readonly string[];
}

export function reviewGameBuilderBrief(draft: GameBuilderBriefDraft, previousBrief: string): ReviewedGameBuilderBrief {
  if (!draft || typeof draft !== 'object' || typeof previousBrief !== 'string') {
    throw new GameBuilderBriefError('invalid_draft', 'The game brief could not be reviewed.');
  }
  const starter = gameBuilderStarter(draft.genre);
  const loop = starter.loops.find(item => item.id === draft.coreLoop);
  const difficulty = GAME_BUILDER_DIFFICULTIES.find(item => item.id === draft.difficulty);
  if (!loop || !difficulty) throw new GameBuilderBriefError('invalid_draft', 'Choose a valid core loop and difficulty.');
  const theme = text(draft.theme, 'Theme', GAME_BUILDER_FIELD_LIMITS.theme);
  const objective = text(draft.objective, 'Player objective', GAME_BUILDER_FIELD_LIMITS.objective);
  const constraints = text(draft.constraints, 'Constraints', GAME_BUILDER_FIELD_LIMITS.constraints, true, true);
  const requirements = [
    'One complete, original game with a title screen, clear controls, a playable core loop, and a visible objective.',
    'Keyboard controls on desktop and labelled touch controls on mobile; keep every primary action reachable.',
    'Readable feedback for player actions, useful health/progress indicators, a distinct win/loss state, and a working restart.',
    'Self-contained offline HTML with procedural visuals; no external assets, network requests, accounts, or purchases.',
  ];
  const body = [
    `Create an original ${draft.genre === 'shooter' ? 'top-down arena shooter' : draft.genre === 'roguelike' ? 'room-based roguelike' : '2D platformer'} as one complete browser-playable prototype.`,
    '', 'CREATOR DESIGN BRIEF', `Theme: ${theme}`, `Core loop: ${loop.description}`,
    `Player objective: ${objective}`, `Difficulty: ${difficulty.title}. ${difficulty.description}`,
    'Scope: one focused 2–5 minute experience. Finish its central interaction before adding optional systems.',
    '', 'REQUIRED PLAYER EXPERIENCE', ...requirements.map((item, index) => `${index + 1}. ${item}`),
    '', 'ACCEPTANCE PLAYTHROUGH TO CHECK', ...starter.acceptance.map((item, index) => `${index + 1}. ${item}`),
    'These are requirements for the generated game, not claims that testing has already passed.',
    ...(constraints ? ['', 'ADDITIONAL CREATOR CONSTRAINTS', constraints] : []),
  ].join('\n');
  return Object.freeze({ schema: 'skeleton.playable.reviewed-brief.v1', previousBrief, text: body,
    genre: draft.genre, requirements: Object.freeze(requirements), acceptance: Object.freeze([...starter.acceptance]) });
}

/** Exact-string fencing prevents a reviewed apply from overwriting later typing. */
export function applyReviewedGameBuilderBrief(review: ReviewedGameBuilderBrief, currentBrief: string,
                                              mode: BriefApplyMode, replaceApproved = false): string {
  if (!review || review.schema !== 'skeleton.playable.reviewed-brief.v1' || typeof currentBrief !== 'string' ||
      typeof review.text !== 'string' || typeof review.previousBrief !== 'string' ||
      (mode !== 'append' && mode !== 'replace')) {
    throw new GameBuilderBriefError('invalid_draft', 'Review a valid game brief before applying it.');
  }
  if (currentBrief !== review.previousBrief) {
    throw new GameBuilderBriefError('draft_changed', 'Your written brief changed after this review. Review again to preserve the latest text.');
  }
  if (mode === 'replace' && currentBrief.trim() && replaceApproved !== true) {
    throw new GameBuilderBriefError('replace_unapproved', 'Approve replacing the existing brief, or add the design below it.');
  }
  const output = mode === 'append' && currentBrief.trim()
    ? `${currentBrief}\n\n--- REVIEWED GAME DESIGN ---\n${review.text}` : review.text;
  if (Array.from(output).length > MAX_GAME_BUILDER_BRIEF_CHARS) {
    throw new GameBuilderBriefError('brief_too_long', 'The combined brief exceeds 6,000 characters. Shorten your written brief or explicitly replace it.');
  }
  return output;
}

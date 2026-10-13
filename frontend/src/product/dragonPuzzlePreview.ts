/**
 * Small deterministic original Sokoban design-preview physics.
 *
 * The preview intentionally has no source/build authority: the Python BFS
 * solver still validates authored boards and the native C game is separately
 * compiled and replayed. This local editor helper accepts only 12x10 ASCII
 * grids, simulates 1..3 crates, supports undo/reset and never executes code.
 */
export type BoardCell = '#' | '.' | '@' | '$' | 'o';
export type PuzzleMove = 'w' | 'a' | 's' | 'd';

export interface EditorPreviewState {
  readonly layout: readonly string[];
  readonly walls: readonly number[];
  readonly goals: readonly number[];
  readonly player: number;
  readonly crates: readonly number[];
  readonly moves: number;
  readonly pushes: number;
  readonly history: readonly {
    player: number; crates: readonly number[]; moves: number; pushes: number;
  }[];
  readonly completed: boolean;
}

const WIDTH = 12;
const HEIGHT = 10;
const TOTAL = WIDTH * HEIGHT;
const MAX_HISTORY = 1024;
const DELTAS: Record<PuzzleMove, readonly [number, number]> = {
  w: [0, -1], a: [-1, 0], s: [0, 1], d: [1, 0],
};

export function parseNativeBoard(layout: readonly string[]): EditorPreviewState {
  if (!Array.isArray(layout) || layout.length !== HEIGHT ||
      !layout.every(line => typeof line === 'string' &&
        /^[#.@$o]{12}$/.test(line))) {
    throw new Error('Original native preview requires a 12×10 strict board');
  }
  const walls: number[] = [];
  const goals: number[] = [];
  const crates: number[] = [];
  let player = -1;
  let heroCount = 0;
  for (let position = 0; position < TOTAL; position++) {
    const character = layout[Math.floor(position / WIDTH)][position % WIDTH];
    if (character === '#') walls.push(position);
    if (character === 'o') goals.push(position);
    if (character === '$') crates.push(position);
    if (character === '@') { player = position; heroCount++; }
  }
  if (heroCount !== 1 || crates.length < 1 || crates.length > 3 ||
      goals.length !== crates.length) {
    throw new Error('Original game needs one player and matching crate/goal counts');
  }
  return {
    layout: [...layout], walls, goals, player, crates,
    moves: 0, pushes: 0, history: [], completed: false,
  };
}

function completed(state: EditorPreviewState, crates: readonly number[]): boolean {
  return crates.length > 0 && crates.every(cell => state.goals.includes(cell));
}

export function stepNativePreview(
  state: EditorPreviewState, action: PuzzleMove | 'undo' | 'reset',
): EditorPreviewState {
  if (action === 'reset') return parseNativeBoard(state.layout);
  if (action === 'undo') {
    const prior = state.history[state.history.length - 1];
    if (!prior) return state;
    return {
      ...state, player: prior.player, crates: [...prior.crates],
      moves: prior.moves, pushes: prior.pushes,
      history: state.history.slice(0, -1),
      completed: completed(state, prior.crates),
    };
  }
  if (!Object.prototype.hasOwnProperty.call(DELTAS, action)) {
    throw new Error('Only original bounded movement controls are allowed');
  }
  const [dx, dy] = DELTAS[action];
  const x = state.player % WIDTH;
  const y = Math.floor(state.player / WIDTH);
  const nx = x + dx; const ny = y + dy;
  if (nx < 0 || nx >= WIDTH || ny < 0 || ny >= HEIGHT) return state;
  const destination = ny * WIDTH + nx;
  if (state.walls.includes(destination)) return state;
  const crateAt = state.crates.indexOf(destination);
  let pushed: number | undefined;
  if (crateAt >= 0) {
    const cx = nx + dx; const cy = ny + dy;
    if (cx < 0 || cx >= WIDTH || cy < 0 || cy >= HEIGHT) return state;
    pushed = cy * WIDTH + cx;
    if (state.walls.includes(pushed) || state.crates.includes(pushed)) return state;
  }
  if (state.history.length >= MAX_HISTORY) return state;
  const crates = [...state.crates];
  if (pushed !== undefined) crates[crateAt] = pushed;
  return {
    ...state,
    player: destination,
    crates,
    moves: state.moves + 1,
    pushes: state.pushes + (pushed !== undefined ? 1 : 0),
    history: [...state.history, {
      player: state.player, crates: [...state.crates],
      moves: state.moves, pushes: state.pushes,
    }],
    completed: completed(state, crates),
  };
}

export function replayNativePreview(layout: readonly string[], events: string): EditorPreviewState {
  if (typeof events !== 'string' || events.length > 400 ||
      !/^[wasdur]*$/.test(events)) {
    throw new Error('Original gameplay replay exceeds bounded source rules');
  }
  let state = parseNativeBoard(layout);
  for (const move of events) {
    state = stepNativePreview(
      state, move === 'u' ? 'undo' : move === 'r' ? 'reset' : move as PuzzleMove,
    );
  }
  return state;
}

export function visibleNativeBoard(state: EditorPreviewState): readonly string[] {
  const grid = state.layout.map(row => row.replace(/[@$o]/g, '.').split(''));
  state.goals.forEach(pos => {
    grid[Math.floor(pos / WIDTH)][pos % WIDTH] = 'o';
  });
  state.crates.forEach(pos => {
    grid[Math.floor(pos / WIDTH)][pos % WIDTH] = '$';
  });
  grid[Math.floor(state.player / WIDTH)][state.player % WIDTH] = '@';
  return grid.map(row => row.join(''));
}

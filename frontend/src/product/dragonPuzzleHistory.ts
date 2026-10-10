/**
 * Deterministic original-game board painting history.
 *
 * Keeps the entire small original campaign in an in-memory reversible stack:
 * undo/redo is global across stage tabs; at most 96 source snapshots survive.
 * Immutable copies protect previous revisions from React render mutations.
 * This is pure game editing data, no filesystem, network, compiler or LLM.
 */
export type PuzzleBoard = readonly string[];
export type PuzzleCampaign = readonly PuzzleBoard[];

export interface PuzzleRevision {
  readonly boards: PuzzleCampaign;
  readonly stage: number;
  readonly paintCount: number;
}
export interface PuzzleHistory {
  readonly previous: readonly PuzzleRevision[];
  readonly current: PuzzleRevision;
  readonly next: readonly PuzzleRevision[];
  readonly maxSteps: number;
}

const WIDTH = 12;
const HEIGHT = 10;
export const EDIT_LIMIT = 96;
const CANVAS = /^[#.@$o]{12}$/;
export const DRAW_TILES = Object.freeze(['#', '.', '@', '$', 'o'] as const);
export type DrawTile = typeof DRAW_TILES[number];

export function validCampaign(boards: unknown): boards is PuzzleCampaign {
  return Array.isArray(boards) && boards.length >= 1 && boards.length <= 8 &&
    boards.every(board => Array.isArray(board) && board.length === HEIGHT &&
      board.every((line: unknown) => typeof line === 'string' &&
        CANVAS.test(line)));
}

function copyBoards(boards: PuzzleCampaign): string[][] {
  return boards.map(board => [...board]);
}

function immutableRevision(boards: PuzzleCampaign, stage: number, paints: number): PuzzleRevision {
  if (!validCampaign(boards) || !Number.isInteger(stage) ||
      stage < 0 || stage >= boards.length ||
      !Number.isInteger(paints) || paints < 0) {
    throw new Error('Invalid original native game edit revision');
  }
  return { boards: copyBoards(boards), stage, paintCount: paints };
}

export function initializePuzzleHistory(
  boards: PuzzleCampaign, stage = 0, maxSteps = EDIT_LIMIT,
): PuzzleHistory {
  if (!Number.isInteger(maxSteps) || maxSteps < 1 || maxSteps > EDIT_LIMIT) {
    throw new Error('Original campaign edit history must be bounded');
  }
  return {
    previous: [], current: immutableRevision(boards, stage, 0),
    next: [], maxSteps,
  };
}

export function paintOriginalCell(
  history: PuzzleHistory, stage: number, x: number, y: number,
  brush: DrawTile,
): PuzzleHistory {
  if (!history || !validCampaign(history.current.boards) ||
      !Number.isInteger(stage) || stage < 0 || stage >= history.current.boards.length ||
      !Number.isInteger(x) || !Number.isInteger(y) ||
      x < 0 || x >= WIDTH || y < 0 || y >= HEIGHT ||
      !DRAW_TILES.includes(brush)) {
    throw new Error('Original game canvas paint is out of bounds');
  }
  const boards = copyBoards(history.current.boards);
  const board = boards[stage];
  const before = board[y][x];
  // Moving the one hero must be a single undoable edit.
  if (brush === '@' && before !== '@') {
    for (let row = 0; row < HEIGHT; row++) {
      board[row] = board[row].replace('@', '.');
    }
  }
  const newCell = before === brush && brush !== '@' ? '.' : brush;
  board[y] = board[y].slice(0, x) + newCell + board[y].slice(x + 1);
  if (boards.every((item, i) => item.every(
    (line, j) => line === history.current.boards[i][j]
  ))) return history;
  const previous = [...history.previous, history.current]
    .slice(-history.maxSteps);
  return {
    previous,
    current: immutableRevision(boards, stage, history.current.paintCount + 1),
    next: [],
    maxSteps: history.maxSteps,
  };
}

export function undoPuzzleEdit(history: PuzzleHistory): PuzzleHistory {
  if (!history.previous.length) return history;
  return {
    ...history,
    previous: history.previous.slice(0, -1),
    current: history.previous[history.previous.length - 1],
    next: [history.current, ...history.next].slice(0, history.maxSteps),
  };
}

export function redoPuzzleEdit(history: PuzzleHistory): PuzzleHistory {
  if (!history.next.length) return history;
  return {
    ...history,
    previous: [...history.previous, history.current].slice(-history.maxSteps),
    current: history.next[0],
    next: history.next.slice(1),
  };
}

export function replacePuzzleCampaign(
  history: PuzzleHistory | null, boards: PuzzleCampaign, stage = 0,
): PuzzleHistory {
  return initializePuzzleHistory(boards, stage, history?.maxSteps ?? EDIT_LIMIT);
}

export function canUndoPuzzle(history: PuzzleHistory): boolean {
  return history.previous.length > 0;
}

export function canRedoPuzzle(history: PuzzleHistory): boolean {
  return history.next.length > 0;
}

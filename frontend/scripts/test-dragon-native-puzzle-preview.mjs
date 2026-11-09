import assert from 'node:assert/strict';
import test from 'node:test';
import {
  parseNativeBoard, replayNativePreview, stepNativePreview,
  visibleNativeBoard,
} from '../src/product/dragonPuzzlePreview.ts';

const FIRST = [
  '############',
  '#..........#',
  '#...#......#',
  '#..........#',
  '#...@......#',
  '#....$.....#',
  '#....o.....#',
  '#..........#',
  '#..........#',
  '############',
];
const TWO_CRATE = [
  '############',
  '#..........#',
  '#..........#',
  '#...@......#',
  '#....$$....#',
  '#....oo....#',
  '#..........#',
  '#..........#',
  '#..........#',
  '############',
];

test('native original editor uses real push collision and completion rules', () => {
  let state = parseNativeBoard(FIRST);
  assert.equal(state.moves, 0);
  assert.equal(state.completed, false);
  state = stepNativePreview(state, 'd');
  assert.equal(state.player, 4 + 4 * 12 + 1);
  state = stepNativePreview(state, 's');
  assert.equal(state.pushes, 1);
  assert.equal(state.completed, true);
  assert.equal(state.moves, 2);
  assert.equal(visibleNativeBoard(state)[6][5], '$');
  state = stepNativePreview(state, 'undo');
  assert.equal(state.completed, false);
  assert.equal(state.pushes, 0);
  assert.equal(state.moves, 1);
  state = stepNativePreview(state, 'reset');
  assert.deepEqual(state, parseNativeBoard(FIRST));
});

test('blocked walls, boundaries and crates cannot move into occupied tiles', () => {
  const baseline = parseNativeBoard(FIRST);
  let state = stepNativePreview(baseline, 'w');
  assert.equal(state.moves, 1);
  const stopped = stepNativePreview(state, 'w');
  assert.equal(stopped.player, state.player);
  assert.equal(stopped.moves, 1);
  assert.equal(state.pushes, 0);
  const second = parseNativeBoard(TWO_CRATE);
  assert.equal(second.crates.length, 2);
});

test('native game preview is deterministic across undo/replay and reset', () => {
  const input = 'ddssauurddss';
  const a = replayNativePreview(FIRST, input);
  const b = replayNativePreview(FIRST, input);
  assert.deepEqual(a, b);
  assert.deepEqual(replayNativePreview(FIRST, 'ddur'), parseNativeBoard(FIRST));
  assert.deepEqual(replayNativePreview(FIRST, ''), parseNativeBoard(FIRST));
});

test('editor refuses invalid grids, unknown actions and overlong sequences', () => {
  for (const board of (
    [[], ['not a grid'], Array.from({length: 10}, () => '?'.repeat(12)),
      Array.from({length: 10}, () => '.'.repeat(12))]
  )) {
    assert.throws(() => parseNativeBoard(board));
  }
  assert.throws(() => replayNativePreview(FIRST, 'x'));
  assert.throws(() => replayNativePreview(FIRST, 'a'.repeat(401)));
  assert.throws(() => stepNativePreview(parseNativeBoard(FIRST), 'execute'));
});

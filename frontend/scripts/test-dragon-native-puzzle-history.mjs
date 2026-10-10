import assert from 'node:assert/strict';
import test from 'node:test';
import {
  initializePuzzleHistory, paintOriginalCell, undoPuzzleEdit,
  redoPuzzleEdit, replacePuzzleCampaign, canUndoPuzzle,
  canRedoPuzzle, validCampaign, EDIT_LIMIT, reorderPuzzleStage,
} from '../src/product/dragonPuzzleHistory.ts';

const BOARD = [
  '############',
  '#..........#',
  '#..........#',
  '#..........#',
  '#...@......#',
  '#....$.....#',
  '#....o.....#',
  '#..........#',
  '#..........#',
  '############',
];
const DIFFERENT = BOARD.map((row,index) => index === 2
  ? '#.###......#' : row);

test('undoing one player relocation restores both former and new hero tiles',()=>{
  const first=initializePuzzleHistory([BOARD]);
  const after=paintOriginalCell(first,0,6,4,'@');
  assert.equal(after.current.boards[0][4][4],'.');
  assert.equal(after.current.boards[0][4][6],'@');
  assert.equal(after.current.paintCount,1);
  assert.deepEqual(undoPuzzleEdit(after).current.boards[0],BOARD);
  assert.deepEqual(redoPuzzleEdit(undoPuzzleEdit(after)).current.boards,
                   after.current.boards);
  assert.equal(first.current.boards[0][4][4],'@');
});

test('painting stage two can be undone from stage one and clears redo on edit',()=>{
  const first=initializePuzzleHistory([BOARD,DIFFERENT]);
  const second=paintOriginalCell(first,1,2,3,'#');
  const third=paintOriginalCell(second,0,3,2,'$');
  const once=undoPuzzleEdit(third);
  assert.equal(once.current.stage,1);
  assert.deepEqual(once.current.boards[0],BOARD);
  assert.equal(once.next.length,1);
  const edit=paintOriginalCell(once,1,2,2,'#');
  assert.equal(edit.next.length,0);
  assert.equal(canRedoPuzzle(edit),false);
  assert.equal(canUndoPuzzle(edit),true);
});

test('redoing preserves original authored world without mutating previous snapshots',()=>{
  const first=initializePuzzleHistory([BOARD]);
  const second=paintOriginalCell(first,0,4,2,'#');
  const third=paintOriginalCell(second,0,4,2,'#');
  assert.equal(third.current.boards[0][2][4],'.');
  assert.equal(second.current.boards[0][2][4],'#');
  const result=redoPuzzleEdit(undoPuzzleEdit(third));
  assert.equal(result.current.boards[0][2][4],'.');
  assert.deepEqual(first.current.boards[0],BOARD);
});

test('bounded undo stack admits at most 96 real edits and no work beyond it',()=>{
  let state=initializePuzzleHistory([BOARD],0);
  for(let n=0;n<EDIT_LIMIT+29;n++){
    state=paintOriginalCell(state,0,2,2,'#');
  }
  assert.equal(state.previous.length,EDIT_LIMIT);
  assert.equal(state.current.paintCount,EDIT_LIMIT+29);
  for(let n=0;n<EDIT_LIMIT;n++)state=undoPuzzleEdit(state);
  assert.equal(canUndoPuzzle(state),false);
  assert.equal(state.next.length,EDIT_LIMIT);
});

test('equal/no-op painting does not manufacture history',()=>{
  const first=initializePuzzleHistory([BOARD]);
  assert.equal(paintOriginalCell(first,0,4,4,'@'),first);
  assert.equal(undoPuzzleEdit(first),first);
  assert.equal(redoPuzzleEdit(first),first);
});

test('import replacement starts a fresh history without sharing stale changes',()=>{
  const first=paintOriginalCell(initializePuzzleHistory([BOARD]),0,3,2,'#');
  const replacement=replacePuzzleCampaign(first,[DIFFERENT]);
  assert.equal(replacement.previous.length,0);
  assert.equal(canUndoPuzzle(replacement),false);
  assert.deepEqual(replacement.current.boards[0],DIFFERENT);
});

test('source authoring stays constrained to proper original grid cells',()=>{
  assert.equal(validCampaign([BOARD]),true);
  assert.equal(validCampaign([]),false);
  assert.equal(validCampaign(Array.from({length:9},()=>BOARD)),false);
  assert.equal(validCampaign([['not a level']]),false);
  for(const bad of [
    [-1,2,'#'],[12,2,'#'],[2,10,'#'],[2,2,'x'],
  ]) {
    assert.throws(()=>paintOriginalCell(initializePuzzleHistory([BOARD]),
     0,bad[0],bad[1],bad[2]));
  }
  assert.throws(()=>initializePuzzleHistory([BOARD],1));
  assert.throws(()=>initializePuzzleHistory([BOARD],0,200));
});



test('reordering actual campaign stages updates export order and survives undo/redo',()=>{
  const first=initializePuzzleHistory([BOARD,DIFFERENT]);
  const moved=reorderPuzzleStage(first,0,1);
  assert.deepEqual(moved.current.boards[0],DIFFERENT);
  assert.deepEqual(moved.current.boards[1],BOARD);
  assert.equal(moved.current.stage,1);
  const restored=undoPuzzleEdit(moved);
  assert.deepEqual(restored.current.boards[0],BOARD);
  assert.deepEqual(restored.current.boards[1],DIFFERENT);
  const done=redoPuzzleEdit(restored);
  assert.deepEqual(done.current.boards,moved.current.boards);
  assert.equal(first.current.boards[0],BOARD);
  assert.equal(reorderPuzzleStage(first,0,0),first);
});

test('native stage reordering rejects out-of-range or noninteger stages',()=>{
  const first=initializePuzzleHistory([BOARD,DIFFERENT]);
  for (const positions of [[-1,0],[0,2],[0,-1],[2,1],[0,0.5]]) {
    assert.throws(()=>reorderPuzzleStage(first,positions[0],positions[1]));
  }
});

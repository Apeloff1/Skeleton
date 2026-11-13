'use strict';
const assert = require('node:assert/strict');
const { test } = require('node:test');
const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');
const { compileFunction } = require('node:vm');
const ts = require('typescript');

const filename = resolve(__dirname, '../src/features/Playable/gameBuilderBrief.ts');
const compiled = ts.transpileModule(readFileSync(filename, 'utf8'), {
  fileName: filename, reportDiagnostics: true,
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
});
assert.equal(compiled.diagnostics.length, 0, 'the production contract must compile');
const moduleRecord = { exports: {} };
compileFunction(compiled.outputText, ['require', 'module', 'exports'])(() => {
  assert.fail('brief composition must not require a network, storage, model or provider dependency');
}, moduleRecord, moduleRecord.exports);
const {
  GAME_BUILDER_STARTERS, GAME_BUILDER_DIFFICULTIES, MAX_GAME_BUILDER_BRIEF_CHARS,
  newGameBuilderDraft, changeGameBuilderStarter, reviewGameBuilderBrief,
  applyReviewedGameBuilderBrief, GameBuilderBriefError,
} = moduleRecord.exports;

function refuses(work, code) {
  assert.throws(work, error => error instanceof GameBuilderBriefError && error.code === code);
}

test('all three starters and every core loop produce a complete bounded design with explicit acceptance', () => {
  assert.deepEqual(GAME_BUILDER_STARTERS.map(item => item.id), ['shooter', 'platformer', 'roguelike']);
  const outputs = new Set();
  for (const starter of GAME_BUILDER_STARTERS) {
    for (const loop of starter.loops) {
      for (const difficulty of GAME_BUILDER_DIFFICULTIES) {
        const draft = { ...newGameBuilderDraft(starter.id), coreLoop: loop.id, difficulty: difficulty.id };
        const result = reviewGameBuilderBrief(draft, 'Existing creator brief');
        assert.equal(result.schema, 'skeleton.playable.reviewed-brief.v1');
        assert.equal(result.genre, starter.id);
        assert.equal(result.previousBrief, 'Existing creator brief');
        assert.ok(result.text.includes(loop.description));
        assert.ok(result.text.includes(difficulty.description));
        assert.ok(result.text.includes(draft.objective));
        assert.ok(result.text.includes('Keyboard controls'));
        assert.ok(result.text.includes('touch controls'));
        assert.ok(result.text.includes('win/loss state'));
        assert.ok(result.text.includes('working restart'));
        assert.ok(result.text.includes('no external assets, network requests'));
        assert.ok(result.text.includes('not claims that testing has already passed'));
        assert.equal(result.requirements.length, 4);
        assert.equal(result.acceptance.length, 3);
        assert.ok(result.text.length < MAX_GAME_BUILDER_BRIEF_CHARS);
        outputs.add(result.text);
      }
    }
  }
  assert.equal(outputs.size, 18, 'genre, loop and difficulty must affect the actual generated brief');
});

test('changing starter follows untouched examples while retaining authored themes, goals and constraints', () => {
  const initial = newGameBuilderDraft('platformer');
  const next = changeGameBuilderStarter(initial, 'shooter');
  assert.equal(next.theme, newGameBuilderDraft('shooter').theme);
  assert.equal(next.objective, newGameBuilderDraft('shooter').objective);
  assert.equal(initial.genre, 'platformer', 'changing a starter does not mutate the previous draft');
  const custom = { ...initial, theme: 'My own underwater city', objective: 'Rescue the cartographer',
    constraints: 'No flashing lights', difficulty: 'relaxed' };
  const switched = changeGameBuilderStarter(custom, 'roguelike');
  assert.equal(switched.theme, custom.theme);
  assert.equal(switched.objective, custom.objective);
  assert.equal(switched.constraints, custom.constraints);
  assert.equal(switched.difficulty, 'relaxed');
  assert.equal(switched.coreLoop, newGameBuilderDraft('roguelike').coreLoop);
});

test('append preserves every byte of creator content and review is immutable after draft changes', () => {
  const original = '  A careful authored idea.\n\nKeep these details exactly.\t\n';
  const draft = newGameBuilderDraft();
  const review = reviewGameBuilderBrief(draft, original);
  const output = applyReviewedGameBuilderBrief(review, original, 'append');
  assert.equal(output.slice(0, original.length), original);
  assert.equal(output, `${original}\n\n--- REVIEWED GAME DESIGN ---\n${review.text}`);
  draft.theme = 'Changed after reviewing';
  assert.ok(!review.text.includes(draft.theme));
  assert.ok(Object.isFrozen(review) && Object.isFrozen(review.requirements) && Object.isFrozen(review.acceptance));
  assert.throws(() => review.acceptance.push('Pretend testing passed'), TypeError);
});

test('replace requires a distinct approval and preserves the reviewed design exactly', () => {
  const original = 'An idea already written by the creator';
  const review = reviewGameBuilderBrief(newGameBuilderDraft(), original);
  refuses(() => applyReviewedGameBuilderBrief(review, original, 'replace'), 'replace_unapproved');
  refuses(() => applyReviewedGameBuilderBrief(review, original, 'replace', 'true'), 'replace_unapproved');
  assert.equal(applyReviewedGameBuilderBrief(review, original, 'replace', true), review.text);
  const empty = reviewGameBuilderBrief(newGameBuilderDraft(), '');
  assert.equal(applyReviewedGameBuilderBrief(empty, '', 'append'), empty.text);
  assert.equal(applyReviewedGameBuilderBrief(empty, '', 'replace'), empty.text);
});

test('typing, deletion and even whitespace changes after review refuse append and approved replace', () => {
  const original = 'My first idea';
  const review = reviewGameBuilderBrief(newGameBuilderDraft(), original);
  for (const changed of ['My second idea', '', original + ' ', '\n' + original]) {
    refuses(() => applyReviewedGameBuilderBrief(review, changed, 'append'), 'draft_changed');
    refuses(() => applyReviewedGameBuilderBrief(review, changed, 'replace', true), 'draft_changed');
  }
});

test('Unicode creator text and multiline constraints survive review as content', () => {
  const draft = { ...newGameBuilderDraft('roguelike'), theme: '月の庭 🌙', objective: 'Find the café’s key 🔑',
    constraints: 'No flashing effects.\nKeep the palette readable.' };
  const review = reviewGameBuilderBrief(draft, '');
  assert.ok(review.text.includes(draft.theme));
  assert.ok(review.text.includes(draft.objective));
  assert.ok(review.text.endsWith(draft.constraints));
});

test('invalid kinds, options, controls, blank goals and oversized fields never produce an applicable review', () => {
  const valid = newGameBuilderDraft();
  for (const change of [
    { genre: 'unknown' }, { coreLoop: 'nonexistent' }, { difficulty: 'impossible' },
    { theme: null }, { theme: 'x'.repeat(161) }, { theme: 'two\nlines' },
    { theme: '\ud800' }, { theme: 'bad\u0000value' },
    { objective: ' ' }, { objective: 7 }, { objective: 'x'.repeat(301) },
    { constraints: 'x'.repeat(601) }, { constraints: false }, { constraints: 'bad\u0001value' },
  ]) {
    refuses(() => reviewGameBuilderBrief({ ...valid, ...change }, ''), 'invalid_draft');
  }
  refuses(() => newGameBuilderDraft('unknown'), 'invalid_draft');
  refuses(() => reviewGameBuilderBrief(null, ''), 'invalid_draft');
  refuses(() => reviewGameBuilderBrief(valid, null), 'invalid_draft');
});

test('a large existing brief is never truncated and requires an explicit smaller replacement', () => {
  const original = 'Creator detail. '.repeat(400);
  const review = reviewGameBuilderBrief(newGameBuilderDraft(), original);
  refuses(() => applyReviewedGameBuilderBrief(review, original, 'append'), 'brief_too_long');
  assert.equal(applyReviewedGameBuilderBrief(review, original, 'replace', true), review.text);
  assert.equal(original, 'Creator detail. '.repeat(400));
});

test('invalid review envelopes and apply modes fail rather than silently replacing a brief', () => {
  const review = reviewGameBuilderBrief(newGameBuilderDraft(), '');
  refuses(() => applyReviewedGameBuilderBrief(null, '', 'append'), 'invalid_draft');
  refuses(() => applyReviewedGameBuilderBrief({ ...review, schema: 'unknown' }, '', 'append'), 'invalid_draft');
  refuses(() => applyReviewedGameBuilderBrief(review, '', 'automatic'), 'invalid_draft');
  refuses(() => applyReviewedGameBuilderBrief(review, null, 'append'), 'invalid_draft');
});

'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { load } = require('../skeleton-forge/harness.cjs');
const { beats } = require('./fixtures/beats.json');

const B = load('src/forgeOperator/beatSummary.ts');
const K = load('src/forgeOperator/catalog.ts');

test('summarizeBeats returns null for null/empty beats', () => {
  assert.equal(B.summarizeBeats(null, {}), null);
  assert.equal(B.summarizeBeats(undefined, {}), null);
  assert.equal(B.summarizeBeats([], {}), null);
});

test('summarizeBeats empty answers: fixture progress 0/11 incomplete', () => {
  const s = B.summarizeBeats(beats, {});
  assert.ok(s);
  assert.equal(s.total, 11, 'era_explicit not required');
  assert.equal(s.answered, 0);
  assert.equal(s.complete, false);
  assert.equal(s.progressLabel, '0 / 11 answered');
  assert.equal(s.cleanedCount, 0);
  assert.deepEqual(s.answerSheet, []);
  assert.equal(s.explicitEra, null);
  assert.equal(s.missing.length, 11);
  assert.ok(!s.missing.includes('era_explicit'));
});

test('summarizeBeats with seededAnswers is complete and omits unspecified era', () => {
  const answers = K.seededAnswers(beats, 42);
  assert.equal(answers.era_explicit, 'unspecified');
  const s = B.summarizeBeats(beats, answers);
  assert.equal(s.complete, true);
  assert.equal(s.answered, 11);
  assert.equal(s.missing.length, 0);
  assert.equal(s.progressLabel, '11 / 11 answered');
  assert.ok(!('era_explicit' in s.cleaned), 'unspecified era omitted from cleaned');
  assert.equal(s.explicitEra, null);
  assert.ok(s.cleanedCount >= 11);
  assert.ok(s.answerSheet.some((line) => /^pace: /.test(line)));
  assert.deepEqual(s.answerSheet, B.formatAnswerSheet(s.cleaned));
});

test('explicit era lands in cleaned when not unspecified', () => {
  const partial = { pace: 'processional', era_explicit: 'soulslike', bogus: 'x' };
  const s = B.summarizeBeats(beats, partial);
  assert.equal(s.cleaned.pace, 'processional');
  assert.equal(s.cleaned.era_explicit, 'soulslike');
  assert.equal(s.explicitEra, 'soulslike');
  assert.ok(!('bogus' in s.cleaned));
  assert.equal(s.answered, 1);
  assert.equal(s.complete, false);
  assert.ok(s.missing.includes('death'));
  assert.ok(s.answerSheet.includes('era_explicit: soulslike'));
  assert.ok(s.answerSheet.includes('pace: processional'));
});

test('formatAnswerSheet sorts keys and skips empties', () => {
  assert.deepEqual(B.formatAnswerSheet(null), []);
  assert.deepEqual(B.formatAnswerSheet(undefined), []);
  assert.deepEqual(B.formatAnswerSheet({}), []);
  assert.deepEqual(B.formatAnswerSheet({ zed: 'a', pace: 'processional', empty: '' }), [
    'pace: processional',
    'zed: a',
  ]);
});

test('progressLabel and isOptionSelected helpers', () => {
  assert.equal(B.progressLabel(null), '0 / 0 answered');
  assert.equal(B.progressLabel({ answered: 3, total: 11, missing: [] }), '3 / 11 answered');
  assert.equal(B.isOptionSelected({ pace: 'processional' }, 'pace', 'processional'), true);
  assert.equal(B.isOptionSelected({ pace: 'processional' }, 'pace', 'frantic'), false);
  assert.equal(B.isOptionSelected(null, 'pace', 'processional'), false);
});

test('complete vs incomplete via partial fixture answers', () => {
  const incomplete = B.summarizeBeats(beats, { pace: 'frantic', death: 'everything' });
  assert.equal(incomplete.complete, false);
  assert.equal(incomplete.answered, 2);
  assert.ok(incomplete.missing.length > 0);

  const allRequired = {};
  for (const b of beats) {
    if (b.id === 'era_explicit') continue;
    allRequired[b.id] = b.options[0];
  }
  const complete = B.summarizeBeats(beats, allRequired);
  assert.equal(complete.complete, true);
  assert.equal(complete.answered, 11);
  assert.equal(complete.missing.length, 0);
  assert.equal(complete.explicitEra, null);
});

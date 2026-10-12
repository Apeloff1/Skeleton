'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { load } = require('../skeleton-forge/harness.cjs');
const { beats } = require('./fixtures/beats.json');
const intakeFixture = require('./fixtures/intake.json');

const I = load('src/forgeOperator/intakeSummary.ts');
const K = load('src/forgeOperator/catalog.ts');

test('summarizeIntakeReadiness empty: cannot submit', () => {
  const s = I.summarizeIntakeReadiness(beats, {});
  assert.equal(s.canSubmit, false);
  assert.equal(s.complete, false);
  assert.equal(s.answered, 0);
  assert.equal(s.total, 11);
  assert.equal(s.cleanedCount, 0);
  assert.deepEqual(s.answerSheet, []);
  assert.equal(s.explicitEra, null);
  assert.match(s.hint, /No cleaned answers/);
  assert.equal(I.intakeA11yLabel(s), 'Intake form not ready');
});

test('summarizeIntakeReadiness with seededAnswers is ready and complete', () => {
  const answers = K.seededAnswers(beats, 42);
  const cleaned = K.cleanAnswers(beats, answers);
  const s = I.summarizeIntakeReadiness(beats, answers);
  assert.equal(s.complete, true);
  assert.equal(s.canSubmit, true);
  assert.equal(s.answered, 11);
  assert.equal(s.explicitEra, null);
  assert.deepEqual(s.cleaned, cleaned);
  assert.ok(s.answerSheet.some((line) => /^pace: /.test(line)));
  assert.match(s.hint, /ballot vote/);
  assert.match(I.intakeA11yLabel(s), /Intake ready/);
});

test('summarizeIntakeReadiness pins explicit era and partial sheets', () => {
  const partial = { pace: 'frantic', death: 'the_raid', era_explicit: 'soulslike' };
  const s = I.summarizeIntakeReadiness(beats, partial);
  assert.equal(s.canSubmit, true);
  assert.equal(s.complete, false);
  assert.equal(s.explicitEra, 'soulslike');
  assert.ok(s.missing.includes('combat'));
  assert.match(s.hint, /Partial sheet/);
  assert.match(I.intakeA11yLabel(s), /Intake partial/);
});

test('formatIntakeAnswers sorts and skips empties', () => {
  assert.deepEqual(I.formatIntakeAnswers(null), []);
  assert.deepEqual(I.formatIntakeAnswers({}), []);
  assert.deepEqual(I.formatIntakeAnswers({ zed: 'a', pace: 'frantic', empty: '' }), [
    'pace: frantic',
    'zed: a',
  ]);
});

test('formatBallotLines / formatBallotLabel from fixture ballots', () => {
  const ballots = intakeFixture.intake.ballots;
  const lines = I.formatBallotLines(ballots);
  assert.ok(lines[0].startsWith('soulslike '));
  assert.match(lines[0], /45% \(5\)/);
  assert.match(I.formatBallotLabel(ballots), /soulslike/);
  assert.equal(I.formatBallotLabel(null), '—');
  assert.deepEqual(I.formatBallotLines({}), []);
});

test('formatDominantAxes reads tensor dominant list', () => {
  assert.equal(I.formatDominantAxes(null), '—');
  assert.equal(I.formatDominantAxes({ era: 'x', axes: {}, dominant: [], fingerprint: 'f' }), '—');
  assert.match(
    I.formatDominantAxes(intakeFixture.intake.tensor),
    /lethality=0\.870/,
  );
});

test('extractIntake and summarizeIntakeResult from fixture payload', () => {
  assert.equal(I.extractIntake(null), null);
  assert.equal(I.extractIntake({}), null);
  const extracted = I.extractIntake(intakeFixture);
  assert.ok(extracted);
  assert.equal(extracted.era, 'soulslike');

  const s = I.summarizeIntakeResult(intakeFixture);
  assert.ok(s);
  assert.equal(s.votedEra, 'soulslike');
  assert.equal(s.succeeded, true);
  assert.equal(s.fingerprint, intakeFixture.intake.tensor.fingerprint);
  assert.match(s.dominant, /lethality=/);
  assert.match(s.ballotLabel, /soulslike/);
  assert.ok(s.ballotLines.length >= 3);
  assert.equal(s.answerCount, 11);
  assert.ok(s.answerSheet.some((l) => l === 'pace: frantic'));
  assert.match(s.vision, /intake pace=frantic/);
  assert.equal(s.runEra, intakeFixture.era);
});

test('summarizeIntakeResult tolerates intake-only payload', () => {
  const s = I.summarizeIntakeResult({ intake: intakeFixture.intake });
  assert.ok(s);
  assert.equal(s.succeeded, null);
  assert.equal(s.runEra, 'soulslike');
  assert.equal(I.summarizeIntakeResult(null), null);
});

test('intakeA11yLabel null-safe', () => {
  assert.equal(I.intakeA11yLabel(null), 'Intake form empty');
  assert.equal(I.intakeA11yLabel(undefined), 'Intake form empty');
});

test('operatorTabs includes intake after beats', () => {
  const T = load('src/forgeOperator/operatorTabs.ts');
  assert.ok(T.OPERATOR_TABS.includes('intake'));
  const beatsIdx = T.OPERATOR_TABS.indexOf('beats');
  const intakeIdx = T.OPERATOR_TABS.indexOf('intake');
  assert.ok(intakeIdx === beatsIdx + 1);
  assert.equal(T.OPERATOR_TAB_LABELS.intake, 'Intake');
  assert.match(T.OPERATOR_TAB_HINTS.intake, /\/api\/v1\/gameforge\/intake/);
  assert.equal(T.parseOperatorTab('intake'), 'intake');
  assert.equal(T.parseOperatorTab('INTAKE'), 'intake');
});


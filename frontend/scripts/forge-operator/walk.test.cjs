'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { load } = require('../skeleton-forge/harness.cjs');
const fixture = require('./fixtures/walk.json');

const W = load('src/forgeOperator/walkSummary.ts');
const clone = (x) => JSON.parse(JSON.stringify(x));

test('summarizeWalk flattens fixture into operator readout', () => {
  const s = W.summarizeWalk(fixture);
  assert.equal(s.verdict, 'passed');
  assert.equal(s.label, 'EXTRACTED');
  assert.match(s.detail, /Extracted in 17\.71s/);
  assert.equal(s.mode, 'ideal');
  assert.equal(s.elapsed, '17.71s');
  assert.equal(s.bound, '8.55s');
  assert.equal(s.hops, 3);
  assert.equal(s.fights, 0);
  assert.equal(s.cores, '1/1');
  assert.equal(s.heatPeak, '0.00');
  assert.equal(s.vents, 0);
  assert.match(s.pathLabel, /r00 → r01 → r00 → r13/);
  assert.ok(s.notes.some((n) => /extracted/.test(n)));
  assert.equal(s.stepCount, 6);
  assert.equal(s.stepsPreview.length, 6);
  assert.match(s.stepsPreview[0], /\[r00\] enter · spawn/);
  assert.equal(s.planEra, 'soulslike');
  assert.equal(s.planSeed, '7facd4753164ff1f');
  assert.equal(s.planBias, 'loot');
  assert.match(s.planOracle, /Very doubtful/);
  assert.match(s.planBriefing, /Jeeves \/ soulslike/);
});

test('summarizeWalk returns null without a walk payload', () => {
  assert.equal(W.summarizeWalk(null), null);
  assert.equal(W.summarizeWalk({}), null);
  assert.equal(W.summarizeWalk({ plan: fixture.plan }), null);
});

test('walkVerdict distinguishes passed, collapsed, and incomplete', () => {
  assert.equal(W.walkVerdict(fixture.walk), 'passed');
  assert.equal(W.walkVerdictLabel('passed'), 'EXTRACTED');

  const collapsed = clone(fixture.walk);
  collapsed.passed = false;
  collapsed.collapsed = true;
  collapsed.extracted = false;
  assert.equal(W.walkVerdict(collapsed), 'collapsed');
  assert.equal(W.walkVerdictLabel('collapsed'), 'COLLAPSED');

  const incomplete = clone(fixture.walk);
  incomplete.passed = false;
  incomplete.collapsed = false;
  incomplete.extracted = false;
  incomplete.cores = 0;
  const s = W.summarizeWalk({ walk: incomplete, plan: fixture.plan });
  assert.equal(s.verdict, 'failed');
  assert.equal(s.label, 'INCOMPLETE');
  assert.match(s.detail, /Did not extract/);
  assert.equal(W.walkVerdict(null), 'unknown');
  assert.equal(W.walkVerdictLabel('unknown'), 'NO WALK');
});

test('formatWalkPath truncates long routes and formatWalkStep renders details', () => {
  assert.equal(W.formatWalkPath([]), '—');
  assert.equal(W.formatWalkPath(null), '—');
  assert.equal(W.formatWalkPath(['a', 'b', 'c']), 'a → b → c');
  const long = Array.from({ length: 12 }, (_, i) => `r${String(i).padStart(2, '0')}`);
  const label = W.formatWalkPath(long, 8);
  assert.match(label, /^r00 → r01 → r02 → r03 → r04 → r05 → r06 → … → r11 \(12 rooms\)$/);
  assert.equal(
    W.formatWalkStep({ t: 4.579, room: 'r01', action: 'loot', detail: 'cores=1' }),
    't=4.58s  [r01] loot · cores=1',
  );
  assert.equal(
    W.formatWalkStep({ t: 0, room: 'r00', action: 'enter' }),
    't=0.00s  [r00] enter',
  );
});

test('summarizePlanBrief tolerates missing plan fields', () => {
  assert.deepEqual(W.summarizePlanBrief(null), {
    planEra: '—',
    planSeed: '—',
    planBriefing: '—',
    planBias: '—',
    planOracle: '—',
  });
  const onlyIndex = W.summarizePlanBrief({ era: 'x', seed: 's', oracle_index: 3 });
  assert.equal(onlyIndex.planOracle, '#3');
});

test('operatorTabs includes walk after plans', () => {
  const T = load('src/forgeOperator/operatorTabs.ts');
  assert.ok(T.OPERATOR_TABS.includes('walk'));
  assert.equal(T.OPERATOR_TAB_LABELS.walk, 'Walk');
  assert.match(T.OPERATOR_TAB_HINTS.walk, /\/api\/skeleton\/walk/);
  assert.equal(T.parseOperatorTab('walk'), 'walk');
  assert.equal(T.parseOperatorTab('WALK'), 'walk');
  assert.equal(T.parseOperatorTab('nope'), null);
});

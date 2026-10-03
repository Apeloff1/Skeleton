'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { load } = require('../skeleton-forge/harness.cjs');
const fixture = require('./fixtures/plan.json');

const P = load('src/forgeOperator/planSummary.ts');
const clone = (x) => JSON.parse(JSON.stringify(x));

test('summarizePlan returns null for null/undefined', () => {
  assert.equal(P.summarizePlan(null), null);
  assert.equal(P.summarizePlan(undefined), null);
});

test('summarizePlan flattens soulslike fixture into operator readout', () => {
  const s = P.summarizePlan(fixture);
  assert.equal(s.era, 'soulslike');
  assert.equal(s.seed, '7facd4753164ff1f');
  assert.equal(s.tensorFp, '4830b90bbe5a0808');
  assert.match(s.oracle, /Very doubtful/);
  assert.match(s.briefing, /Jeeves \/ soulslike/);
  assert.equal(s.roomBias, 'loot');
  assert.equal(s.adapt, 'none');
  assert.equal(s.slack, '0.00');
  assert.equal(s.authored, 'cortex');
  assert.equal(s.spawnWeapon, false);
  assert.equal(s.extractLate, true);
  assert.equal(s.enemyMixLabel, 'trash×2 · elite×2');
  assert.equal(s.recipesLabel, 'kinetic_basic, kinetic_heavy');
  assert.ok(s.notes.some((n) => /late_extract=1/.test(n)));
  assert.ok(s.notes.length <= 8);
  assert.ok(s.flags.includes('extract_late'));
  assert.ok(s.flags.includes('authored'));
  assert.ok(!s.flags.includes('spawn_weapon'));
  assert.ok(!s.flags.includes('slack')); // slack is 0
  assert.ok(!s.flags.includes('adapt')); // adapt is none
  assert.ok(s.flagLabels.includes('late extract'));
  assert.ok(s.flagLabels.some((l) => /authored cortex/.test(l)));
});

test('summarizePlan oracle falls back to #index', () => {
  const onlyIndex = P.summarizePlan({ era: 'x', seed: 's', oracle_index: 3 });
  assert.equal(onlyIndex.oracle, '#3');
  assert.equal(onlyIndex.enemyMixLabel, '—');
  assert.equal(onlyIndex.recipesLabel, '—');
  assert.deepEqual(onlyIndex.notes, []);
  assert.deepEqual(onlyIndex.flagLabels, []);
});

test('formatEnemyMix handles empty, zeros, and sparse mixes', () => {
  assert.equal(P.formatEnemyMix(null), '—');
  assert.equal(P.formatEnemyMix(undefined), '—');
  assert.equal(P.formatEnemyMix({}), '—');
  assert.equal(P.formatEnemyMix({ trash: 0, elite: 0 }), '—');
  assert.equal(P.formatEnemyMix({ trash: 2, elite: 2, boss: 0 }), 'trash×2 · elite×2');
  assert.equal(P.formatEnemyMix({ boss: 1 }), 'boss×1');
});

test('formatRecipes joins and truncates', () => {
  assert.equal(P.formatRecipes(null), '—');
  assert.equal(P.formatRecipes([]), '—');
  assert.equal(P.formatRecipes(['a', 'b']), 'a, b');
  assert.equal(P.formatRecipes(['a', 'b', 'c', 'd'], 2), 'a, b … (+2)');
  assert.equal(P.formatRecipes(['kinetic_basic', 'kinetic_heavy']), 'kinetic_basic, kinetic_heavy');
});

test('collectPlanFlags / planFlagLabel cover spawn and slack', () => {
  const armed = clone(fixture);
  armed.spawn_weapon = true;
  armed.extract_late = false;
  armed.slack = 1.25;
  armed.adapt = 'tighten';
  armed.authored = '';
  const { flags, flagLabels } = P.collectPlanFlags(armed);
  assert.deepEqual(flags, ['spawn_weapon', 'adapt', 'slack']);
  assert.ok(flagLabels.includes('spawn weapon'));
  assert.ok(flagLabels.includes('adapt tighten'));
  assert.ok(flagLabels.includes('slack 1.25'));
  assert.equal(P.planFlagLabel('extract_late'), 'late extract');
  assert.equal(P.planFlagLabel('spawn_weapon'), 'spawn weapon');
});

test('operatorTabs still lists plans and walk', () => {
  const T = load('src/forgeOperator/operatorTabs.ts');
  assert.ok(T.OPERATOR_TABS.includes('plans'));
  assert.ok(T.OPERATOR_TABS.includes('walk'));
  assert.equal(T.OPERATOR_TAB_LABELS.plans, 'Plans');
  assert.equal(T.parseOperatorTab('plans'), 'plans');
});

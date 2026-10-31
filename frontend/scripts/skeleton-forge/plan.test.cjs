'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { load } = require('./harness.cjs');
const runFixture = require('./fixtures/run.json');

const P = load('src/skeletonForge/plan.ts');

const ERAS = [
  { id: 'boomer_shooter', primary_dps: 121.8, speed: 320, ttk: { trash: 0.4, elite: 2, boss: 30 }, philosophy: 'movement_gun_poetry' },
  { id: 'soulslike', primary_dps: 40, speed: 110, ttk: { trash: 3, elite: 12, boss: 90 }, philosophy: 'learn_the_pattern' },
];

test('fixture plan: era link, veto fit, and slack unknown with no prior walk', () => {
  const v = P.planView(runFixture, ERAS, 'boomer_shooter');
  assert.equal(v.present, true);
  assert.equal(v.era, 'boomer_shooter');
  assert.equal(v.bias, 'combat');
  assert.equal(v.armed, true);
  assert.equal(v.extractLate, true);
  assert.equal(v.adapt, 'none');
  assert.equal(v.slack, null, 'adapt=none is the no-walk sentinel, not zero slack');
  assert.equal(P.formatSlack(v.slack), 'unknown');
  assert.equal(v.veto.state, 'fits');
  assert.equal(v.veto.spanS, 15.9);
  assert.equal(v.veto.budgetS, 140);
  assert.equal(v.link.relation, 'match');
  assert.equal(v.link.honoursPin, true);
  const trash = v.mix.find((m) => m.tier === 'trash');
  assert.equal(trash.count, 4);
  assert.equal(trash.ttkS, 0.4);
  assert.equal(trash.subtotalS, 1.6);
  assert.equal(v.totalEnemies, 6);
  assert.equal(v.naiveCombatS, 5.6);
  assert.match(P.describePlan(v), /Build plan for Boomer Shooter/);
  assert.match(P.describePlan(v), /Slack unknown/);
  const status = P.planStatus(runFixture, false, v);
  assert.equal(status.state, 'ready');
});

test('learned notes: improved, invented, imported mix and moe share one kind', () => {
  const kinds = [
    'improved mix trash=2 elite=1 boss=0',
    'invented bias=loot slack=0.40',
    'imported mix — no search',
    'moe mix trash=3 elite=1 boss=1 slack=0.55',
    'moe bias=heat',
    'left-veto mix irreducible thermal_span=90.0s',
    'cortex: slack=0.10 hops=2 — drop late extract',
    'bias=combat',
    'free text',
  ].map(P.classifyNote);
  assert.deepEqual(kinds.map((n) => n.kind), [
    'invented', 'invented', 'invented', 'invented', 'invented', 'veto', 'cortex', 'fact', 'other',
  ]);
  assert.equal(P.noteKindLabel(kinds[2]), 'Imported');
  assert.equal(P.noteKindLabel(kinds[3]), 'Mixture of experts');
  assert.equal(P.noteKindLabel(kinds[5]), 'Veto');
  const pruned = P.vetoFromNotes([P.classifyNote('left-veto dropped elite,boss thermal_span=40.0s')]);
  assert.equal(pruned.state, 'pruned');
  assert.deepEqual(pruned.dropped, ['elite', 'boss']);
});

test('slack stays a measurement when a prior walk adapted the plan', () => {
  const base = runFixture.build_plan;
  const hold = P.planView({
    ...runFixture,
    build_plan: { ...base, adapt: 'hold', slack: 0.42, notes: ['cortex: slack=0.42 — hold the last plan grain'] },
  });
  assert.equal(hold.slack, 0.42);
  assert.equal(P.formatSlack(hold.slack), '42%');
  const ease = P.planView({ ...runFixture, build_plan: { ...base, adapt: 'ease', slack: 0 } });
  assert.equal(ease.slack, 0);
  assert.equal(P.formatSlack(ease.slack), '0%');
  const over = P.planView({ ...runFixture, build_plan: { ...base, adapt: 'harden', slack: 4 } });
  assert.equal(over.slack, 1);
  const missing = P.planView({ era: 'soulslike' });
  assert.equal(missing.present, false);
  assert.equal(missing.slack, null);
  assert.equal(P.planStatus(null).state, 'empty');
  assert.equal(P.planStatus(runFixture, true).state, 'planning');
});

test('era linkage: blend, drift, and a plan that ignores the pin', () => {
  const blend = P.eraLink('boomer_shooter', 'boomer_shooter~soulslike@0.30', null, null);
  assert.equal(blend.relation, 'blend');
  const drift = P.eraLink('boomer_shooter', 'soulslike', 'soulslike', null);
  assert.equal(drift.relation, 'drift');
  assert.equal(drift.honoursPin, false);
  assert.equal(P.eraLink(null, 'soulslike', null, null).relation, 'unknown');
});

test('plan status degrades when the mix cannot fit or the sim failed', () => {
  const overBudget = {
    era: 'soulslike',
    build_plan: {
      era: 'soulslike', adapt: 'hold', slack: 0.2,
      notes: ['left-veto mix irreducible thermal_span=90.0s'],
      enemy_mix: { trash: 1 },
    },
    sim: { passed: true },
    run: { stages: [{ name: 'oracle', status: 'succeeded' }, { name: 'jeeves', status: 'succeeded' }, { name: 'sim', status: 'succeeded' }] },
  };
  assert.equal(P.planStatus(overBudget, false, P.planView(overBudget)).state, 'degraded');
  const simFail = { ...runFixture, sim: { ...runFixture.sim, passed: false } };
  assert.equal(P.planStatus(simFail).state, 'degraded');
  const jeevesFail = {
    ...runFixture,
    run: { stages: [{ name: 'jeeves', status: 'failed' }, { name: 'oracle', status: 'succeeded' }] },
  };
  assert.equal(P.planStatus(jeevesFail).state, 'failed');
});

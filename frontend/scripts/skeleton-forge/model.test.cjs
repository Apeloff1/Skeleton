'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { load } = require('./harness.cjs');
const runFixture = require('./fixtures/run.json');

const Q = load('src/skeletonForge/questionnaire.ts');
const R = load('src/skeletonForge/run.ts');
const E = load('src/skeletonForge/eras.ts');
const C = load('src/skeletonForge/cockpit.ts');

const reduce = (actions, s = Q.INITIAL_STATE) => actions.reduce(Q.questionnaireReducer, s);

test('questionnaire: vision gate, next/back, goto guards', () => {
  let s = reduce([{ type: 'next' }]);
  assert.equal(s.step, 'vision', 'cannot advance with nothing entered');
  assert.match(Q.blockReason(s), /Describe your game/);
  assert.equal(reduce([{ type: 'goto', step: 'review' }]).step, 'vision');
  s = reduce([{ type: 'setVision', vision: 'a heist' }, { type: 'next' }, { type: 'next' }]);
  assert.equal(s.step, 'beats');
  s = reduce([{ type: 'back' }], s);
  assert.equal(s.step, 'brief');
  assert.equal(reduce([{ type: 'goto', step: 'review' }], s).step, 'review');
  assert.equal(reduce([{ type: 'back' }]).step, 'vision', 'back at first step is a no-op');
  const end = reduce([{ type: 'goto', step: 'review' }, { type: 'next' }], s);
  assert.equal(end.step, 'review', 'next at last step is a no-op');
});

test('questionnaire: a brief facet alone unblocks the vision step', () => {
  const s = reduce([{ type: 'setBrief', facet: 'genre', value: 'rpg' }, { type: 'next' }]);
  assert.equal(s.step, 'brief');
});

test('questionnaire: toggling answers and option defaults', () => {
  let s = reduce([
    { type: 'setBeat', beat: 'pace', value: 'frantic' },
    { type: 'setBeat', beat: 'pace', value: 'frantic' },
  ]);
  assert.deepEqual(s.beats, {}, 'selecting the same option twice clears it');
  s = reduce([{ type: 'setOption', key: 'archetype', value: null }, { type: 'setOption', key: 'era', value: 'soulslike' }]);
  assert.equal(s.options.archetype, 'auto');
  assert.equal(s.options.era, 'soulslike');
  s = reduce([{ type: 'setOption', key: 'era', value: '' }], s);
  assert.equal(s.options.era, null);
  assert.deepEqual(reduce([{ type: 'reset' }], s), Q.INITIAL_STATE);
});

test('questionnaire: run request merges brief + beats with beats authoritative', () => {
  const s = reduce([
    { type: 'setVision', vision: '  co-op heist with a butler  ' },
    { type: 'setBrief', facet: 'genre', value: 'rpg' },
    { type: 'setBrief', facet: 'combat', value: 'melee' },
    { type: 'setBeat', beat: 'combat', value: 'earned' },
    { type: 'setOption', key: 'target', value: 'json' },
  ]);
  const req = Q.buildRunRequest(s);
  assert.deepEqual(req, {
    vision: 'co-op heist with a butler', era: null, archetype: 'auto', target: 'json', generation: null,
    answers: { genre: 'rpg', combat: 'earned' },
  });
  assert.deepEqual(Q.shadowedBriefFacets(s), ['combat']);
  assert.equal(Q.eraSource(s), 'beats');
  assert.equal(Q.eraSource(reduce([{ type: 'setBrief', facet: 'genre', value: 'rpg' }])), 'brief');
  assert.equal(Q.eraSource(Q.INITIAL_STATE), 'vision');
});

test('questionnaire: progress counts vision, brief and beats', () => {
  const s = reduce([{ type: 'setVision', vision: 'x' }, { type: 'setBrief', facet: 'theme', value: 'noir' }, { type: 'setBeat', beat: 'ai', value: 'kind' }]);
  const p = Q.progress(s);
  assert.equal(p.total, 1 + 5 + 12);
  assert.equal(p.answered, 3);
  assert.equal(p.beatsAnswered, 1);
  assert.ok(p.ratio > 0.16 && p.ratio < 0.17);
});

test('questionnaire: fallback beats mirror the backend beat ids', () => {
  assert.deepEqual(Q.FALLBACK_BEATS.map((b) => b.id), ['pace', 'death', 'combat', 'info', 'loot', 'heat', 'author', 'social', 'space', 'fail_state', 'ai', 'era_explicit']);
});

test('run summary: real payload → stages, verify, repair, era, blueprint', () => {
  const s = R.summarizeRun(runFixture);
  assert.equal(s.succeeded, true);
  assert.equal(s.era, 'boomer_shooter');
  assert.match(s.blueprintId, /^bp-/);
  assert.equal(s.fileCount, 24);
  assert.equal(s.total, 10);
  assert.equal(s.completed, 10);
  assert.equal(s.failedStage, null);
  assert.equal(s.verify.state, 'passed');
  assert.equal(s.verify.rounds, 1);
  assert.equal(s.verify.threshold, 0.7);
  assert.equal(R.formatScore(s.verify.score), '90%');
  assert.equal(s.repair.state, 'not-needed');
  assert.equal(s.playtest.state, 'off');
  assert.deepEqual(s.composedFeatures, ['crafting', 'collapse', 'extraction', 'companion']);
  assert.equal(s.ledgerValid, true);
  assert.ok(s.advice && s.advice.length > 5);
});

test('run summary: failed verify + repair + failed stage + playtest', () => {
  const p = JSON.parse(JSON.stringify(runFixture));
  p.succeeded = false;
  p.run.stages[5] = { name: 'forge', status: 'FAILED', attempts: 2, duration_s: 1.25, error: 'boom' };
  p.forge.verify_loop = { accepted: false, stopped_reason: 'max_rounds', trace: { rounds: 3, history: [0.4, 0.5, 0.55] } };
  p.forge.verification = { accepted: false, blocking_issues: ['a', 'b'] };
  p.forge.repair = { strategy: 'regen', round: 2, files: { nested: true } };
  p.playtest = { status: 'failed', passed: false };
  const s = R.summarizeRun(p);
  assert.equal(s.failedStage.name, 'forge');
  assert.equal(s.failedStage.durationMs, 1250);
  assert.equal(s.failedStage.error, 'boom');
  assert.equal(s.verify.state, 'failed');
  assert.equal(s.verify.score, 0.55);
  assert.equal(s.verify.blocking, 2);
  assert.equal(s.repair.state, 'unresolved');
  assert.equal(s.repair.detail, 'strategy: regen · round: 2');
  assert.equal(s.playtest.state, 'failed');
  p.forge.verify_loop.accepted = true;
  assert.equal(R.summarizeRun(p).repair.state, 'applied');
});

test('run summary: tolerates null / empty payloads', () => {
  const s = R.summarizeRun(null);
  assert.equal(s.succeeded, false);
  assert.equal(s.total, 10);
  assert.equal(s.verify.state, 'unknown');
  assert.equal(s.repair.state, 'unknown');
  assert.equal(R.pendingStages().every((x) => x.status === 'pending'), true);
  assert.equal(R.formatElapsed(65000), '1m 05s');
  assert.equal(R.formatElapsed(-5), '0s');
  const extra = R.stageViews([{ name: 'playtest', status: 'SKIPPED' }]);
  assert.equal(extra[extra.length - 1].name, 'playtest');
  assert.equal(extra[extra.length - 1].tone, 'warn');
});

const ERAS = [
  { id: 'extraction_now', primary_dps: 108, speed: 195, ttk: { trash: 1.1, elite: 4.5, boss: 60 }, philosophy: 'risk_session_value' },
  { id: 'boomer_shooter', primary_dps: 121.8, speed: 320, ttk: { trash: 0.4 }, philosophy: 'flow_mastery' },
  { id: 'cozy_wholesome', primary_dps: 20, speed: 140, ttk: {}, philosophy: 'comfort' },
];

test('eras: normalisation, filter, sort, blend base', () => {
  const v = E.eraViews(ERAS);
  assert.equal(v[1].dpsRatio, 1);
  assert.equal(v[1].speedRatio, 1);
  assert.equal(v[2].ttkTrash, null);
  assert.equal(v[0].label, 'Extraction Now');
  assert.equal(v[0].philosophy, 'Risk Session Value');
  assert.deepEqual(E.sortEras(v, 'dps').map((x) => x.id), ['boomer_shooter', 'extraction_now', 'cozy_wholesome']);
  assert.deepEqual(E.sortEras(v, 'ttk').map((x) => x.id), ['boomer_shooter', 'extraction_now', 'cozy_wholesome']);
  assert.deepEqual(E.sortEras(v, 'name').map((x) => x.id), ['boomer_shooter', 'cozy_wholesome', 'extraction_now']);
  assert.deepEqual(E.filterEras(v, 'comfort').map((x) => x.id), ['cozy_wholesome']);
  assert.equal(E.filterEras(v, '  ').length, 3);
  assert.equal(E.baseEra('soulslike~jrpg@0.50'), 'soulslike');
  assert.equal(E.baseEra(null), null);
  assert.match(E.describeEra(v[0]), /trash time-to-kill 1.1s/);
  assert.deepEqual(E.eraViews(null), []);
});

test('cockpit: command validation and summaries', () => {
  assert.equal(C.checkCommand('  status ').ok, true);
  assert.equal(C.checkCommand('bind   archetype auto').command, 'bind archetype auto');
  assert.match(C.checkCommand('FROB').error, /Unknown verb/);
  assert.match(C.checkCommand('COMPOSE   ').error, /needs a vision/);
  assert.match(C.checkCommand('BIND ARCHETYPE').error, /BIND ARCHETYPE/);
  assert.equal(C.checkCommand('').ok, false);
  assert.equal(C.summarizeCockpit('BIND ARCHETYPE auto', { archetype: 'auto', composed: true }), 'Archetype pinned: auto (composes from vision)');
  assert.equal(C.summarizeCockpit('COMPOSE x', { summary: '2 systems: heat, hud' }), '2 systems: heat, hud');
  assert.match(C.summarizeCockpit('STATUS', { tensor: { era: 'jrpg' }, ledger: { height: 3, valid: false } }), /Era jrpg · ledger 3 blocks \(INVALID\)/);
  const log = Array.from({ length: 50 }, (_, i) => ({ id: i })).reduce((acc, e) => C.pushEntry(acc, e, 40), []);
  assert.equal(log.length, 40);
  assert.equal(log[0].id, 49);
});

'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { load } = require('./harness.cjs');
const composeFixture = require('./fixtures/compose.json');

const m = load('src/skeletonForge/cockpitScreen.ts');

test('deep-link tab parsing accepts aliases and rejects junk', () => {
  assert.equal(m.parseTabParam('run'), 'run');
  assert.equal(m.parseTabParam(' Questionnaire '), 'build');
  assert.equal(m.parseTabParam(['graph', 'eras']), 'compose');
  assert.equal(m.parseTabParam('forge-run'), 'run');
  assert.equal(m.parseTabParam('cli'), 'console');
  assert.equal(m.parseTabParam('nope'), null);
  assert.equal(m.parseTabParam(undefined), null);
  assert.equal(m.parseTabParam(7), null);
});

test('initial state honours deep link and records the visit', () => {
  const s = m.initialScreenState('eras');
  assert.equal(s.tab, 'eras');
  assert.deepEqual(s.visited, ['eras']);
  assert.equal(m.initialScreenState().tab, 'build');
});

test('tab navigation wraps and tracks visited tabs', () => {
  let s = m.initialScreenState();
  s = m.cockpitScreenReducer(s, { type: 'nextTab', dir: -1 });
  assert.equal(s.tab, 'console');
  s = m.cockpitScreenReducer(s, { type: 'nextTab', dir: 1 });
  assert.equal(s.tab, 'build');
  s = m.cockpitScreenReducer(s, { type: 'tab', tab: 'compose' });
  assert.deepEqual(s.visited, ['build', 'console', 'compose']);
  const same = m.cockpitScreenReducer(s, { type: 'tab', tab: 'bogus' });
  assert.equal(same, s);
});

test('run start jumps to run tab; unseen result badge clears on visit', () => {
  let s = m.initialScreenState();
  s = m.cockpitScreenReducer(s, { type: 'runStarted' });
  assert.equal(s.tab, 'run');
  assert.equal(s.runSeq, 1);
  assert.equal(s.runSeen, 1);
  s = m.cockpitScreenReducer(s, { type: 'tab', tab: 'eras' });
  s = m.cockpitScreenReducer(s, { type: 'runStarted' });
  s = m.cockpitScreenReducer(s, { type: 'tab', tab: 'build' });
  // A run started then the user left before looking at the new one? runStarted visits run, so seen.
  assert.equal(m.tabBadges(s, { runPhase: 'done' }).run.text, '✓');
  const unseen = { ...s, runSeq: s.runSeq + 1 };
  const b = m.tabBadges(unseen, { runPhase: 'done' }).run;
  assert.equal(b.text, '●');
  assert.equal(b.a11y, 'new result');
});

test('era handoffs: use-in-forge returns to questionnaire, view-era opens viewer', () => {
  let s = m.initialScreenState('run');
  s = m.cockpitScreenReducer(s, { type: 'viewEra', era: 'boomer_shooter' });
  assert.equal(s.tab, 'eras');
  assert.equal(s.selectedEra, 'boomer_shooter');
  s = m.cockpitScreenReducer(s, { type: 'useEra', era: 'soulslike' });
  assert.equal(s.tab, 'build');
  assert.equal(s.selectedEra, 'soulslike');
  s = m.cockpitScreenReducer(s, { type: 'selectEra', era: null });
  assert.equal(s.selectedEra, null);
});

test('badges reflect every panel signal', () => {
  const s = m.initialScreenState();
  const b = m.tabBadges(s, {
    runPhase: 'running', composeLoading: true, erasCount: 12, consoleErrors: 2, questionnaireStep: 1, questionnaireSteps: 5,
  });
  assert.deepEqual([b.run.text, b.run.tone], ['…', 'warn']);
  assert.deepEqual([b.compose.text, b.compose.tone], ['…', 'warn']);
  assert.equal(b.eras.text, '12');
  assert.deepEqual([b.console.text, b.console.tone], ['2', 'bad']);
  assert.equal(b.build.text, '2/5');
  assert.equal(b.build.a11y, 'step 2 of 5');
  const e = m.tabBadges(s, { runPhase: 'error', composeError: 'x', erasError: 'down', composeSystems: 3 });
  assert.equal(e.run.tone, 'bad');
  assert.equal(e.compose.a11y, 'compose error');
  assert.equal(e.eras.a11y, 'eras unavailable');
  const ok = m.tabBadges(s, { runPhase: 'idle', composeSystems: 3 });
  assert.equal(ok.compose.text, '3');
  assert.equal(ok.run.text, null);
  assert.equal(ok.console.text, null);
});

test('tab accessibility label carries position and status', () => {
  assert.equal(m.tabA11yLabel('run', { text: '…', tone: 'warn', a11y: 'forging' }), 'Forge run, tab 3 of 5, forging');
  assert.equal(m.tabA11yLabel('build', { text: null, tone: 'idle', a11y: '' }), 'Questionnaire, tab 1 of 5');
});

test('history recall is shell-like and de-duplicated', () => {
  const h = ['STATUS', 'ROLL ORACLE', 'STATUS', 'COMPOSE a heist'];
  let r = m.recallCommand(h, -1, 1);
  assert.deepEqual(r, { cursor: 0, command: 'STATUS' });
  r = m.recallCommand(h, r.cursor, 1);
  assert.equal(r.command, 'ROLL ORACLE');
  r = m.recallCommand(h, r.cursor, 1);
  assert.equal(r.command, 'COMPOSE a heist');
  r = m.recallCommand(h, r.cursor, 1);
  assert.equal(r.command, 'COMPOSE a heist');
  r = m.recallCommand(h, 0, -1);
  assert.deepEqual(r, { cursor: -1, command: '' });
  assert.deepEqual(m.recallCommand([], -1, 1), { cursor: -1, command: '' });
});

test('console failure count and compose summary', () => {
  assert.equal(m.consoleFailures([{ ok: true }, { ok: false }, { ok: false }]), 2);
  assert.equal(m.composeSummaryOf(null), null);
  assert.equal(m.composeSummaryOf({ ...composeFixture, summary: '  Craft & survive  ' }), 'Craft & survive');
  const s = m.composeSummaryOf({ ...composeFixture, summary: undefined });
  assert.match(s, /^Composes \d+ systems?: player, crafting/);
  assert.equal(m.composeSummaryOf({ ...composeFixture, summary: '', components: [] }), null);
});

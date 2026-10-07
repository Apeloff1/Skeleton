'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { h, load, render, text, attrs } = require('./harness.cjs');

const Q = load('src/skeletonForge/questionnaire.ts');
const Flow = load('src/skeletonForge/components/QuestionnaireFlow.tsx').default;

const ERAS = [{ id: 'soulslike', primary_dps: 1, speed: 1, ttk: {}, philosophy: 'x' }, { id: 'jrpg', primary_dps: 1, speed: 1, ttk: {}, philosophy: 'y' }];
const at = (step, extra = {}) => ({ ...Q.INITIAL_STATE, vision: 'a heist with a butler', ...extra, step });
const view = (state, more = {}) => render(h(Flow, { state, dispatch: () => {}, beats: Q.FALLBACK_BEATS, beatsLive: true, eras: ERAS, onForge: () => {}, ...more }));

test('stepper exposes five tabs with position, done and current state', () => {
  const html = view(at('beats'));
  const tabs = attrs(html, 'aria-label').filter((l) => l.startsWith('Step '));
  assert.deepEqual(tabs, [
    'Step 1 of 5: Vision, done', 'Step 2 of 5: Creative brief, done', 'Step 3 of 5: Design beats, current',
    'Step 4 of 5: Forge options', 'Step 5 of 5: Review & forge',
  ]);
  assert.match(html, /role="tablist"/);
  assert.match(html, /role="progressbar"/);
});

test('vision step blocks Next with an explanation until something is entered', () => {
  const html = view({ ...Q.INITIAL_STATE });
  assert.match(text(html), /Describe your game in a sentence or two/);
  const next = html.match(/<button[^>]*data-testid="q-next"[^>]*>/)[0];
  assert.match(next, /aria-disabled="true"|disabled=""/);
  assert.match(html, /aria-label="Game vision"/);
  const back = html.match(/<button[^>]*data-testid="q-back"[^>]*>/)[0];
  assert.match(back, /aria-disabled="true"|disabled=""/);
});

test('brief step renders five radiogroups with the chosen option marked', () => {
  const html = view(at('brief', { brief: { genre: 'rpg' } }));
  const groups = html.match(/role="radiogroup"/g) || [];
  assert.equal(groups.length, 5);
  assert.ok(attrs(html, 'aria-label').includes('Rpg, selected'));
  assert.match(text(html), /✓ Rpg/);
});

test('beats step shows all twelve beats, count, and offline notice', () => {
  const html = view(at('beats', { beats: { pace: 'frantic', ai: 'kind' } }), { beatsLive: false });
  assert.match(text(html), /2\/12 beats answered/);
  assert.match(text(html), /Offline copy/);
  assert.match(text(html), /12\. If you already know the dialect\?/);
  assert.ok(attrs(html, 'aria-label').includes('Frantic, selected'));
});

test('options step: archetype radios, era chips and generations', () => {
  const html = view(at('options', { options: { ...Q.INITIAL_STATE.options, era: 'jrpg' } }), { generations: [{ key: 'snes', label: 'SNES' }] });
  const labels = attrs(html, 'aria-label');
  assert.ok(labels.some((l) => l.startsWith('Compose from vision.') && l.endsWith('Selected.')));
  assert.ok(labels.includes('Era override'));
  assert.match(text(html), /✓ Jrpg/);
  assert.match(text(html), /SNES/);
  assert.match(text(html), /recommended/);
});

test('review step summarises the run request, era source and shadowed facets', () => {
  const state = at('review', { brief: { combat: 'melee', genre: 'rpg' }, beats: { combat: 'earned' } });
  const html = view(state, { composeSummary: '2 systems: companion, extraction' });
  const t = text(html);
  assert.match(t, /Vision a heist with a butler/);
  assert.match(t, /Systems 2 systems: companion, extraction/);
  assert.match(t, /Era is voted by your design beats/);
  assert.match(t, /overrides the brief answer for: combat/);
  assert.match(t, /⚒ Forge it/);
  const busy = view(state, { forging: true });
  assert.match(text(busy), /⚒ Forge it…/);
  assert.match(busy.match(/<button[^>]*data-testid="q-forge"[^>]*>/)[0], /aria-busy="true"/);
});

'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { h, load, render, text } = require('./harness.cjs');
const Q = load('src/skeletonForge/questionnaire.ts');
const Flow = load('src/skeletonForge/components/QuestionnaireFlow.tsx').default;
test('opt-in complete Galaxy save can be restored from the guided Forge options', () => {
  const markup = render(h(Flow, {
    state: { ...Q.INITIAL_STATE, step: 'options' }, dispatch: () => {},
    beats: Q.FALLBACK_BEATS, onForge: () => {},
    onRestoreGalaxyProfile: () => {},
  }));
  assert.match(markup, /data-testid="q-galaxy-restore-saved"/);
  assert.match(text(markup), /Restore saved full Galaxy design/);
});
test('restore control is absent without an approved callback', () => {
  const markup = render(h(Flow, {
    state: { ...Q.INITIAL_STATE, step: 'options' }, dispatch: () => {},
    beats: Q.FALLBACK_BEATS, onForge: () => {},
  }));
  assert.doesNotMatch(markup, /data-testid="q-galaxy-restore-saved"/);
});

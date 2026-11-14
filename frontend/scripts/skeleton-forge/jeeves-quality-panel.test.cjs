'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { h, load, render, text } = require('./harness.cjs');
const Q = load('src/skeletonForge/questionnaire.ts');
const Flow = load('src/skeletonForge/components/QuestionnaireFlow.tsx').default;
test('Jeeves game-quality inspector is collapsed and does not run a model', () => {
  const html = render(h(Flow, {
    state: { ...Q.INITIAL_STATE, step: 'options' }, beats: Q.FALLBACK_BEATS,
    dispatch: () => {}, onForge: () => {},
  }));
  assert.match(html, /data-testid="q-jeeves-quality-panel"/);
  assert.match(html, /data-testid="q-jeeves-quality-toggle"/);
  assert.doesNotMatch(html, /data-testid="q-jeeves-quality-detail"/);
  assert.match(text(html), /Inspect Jeeves local game-quality diagnostics/);
});

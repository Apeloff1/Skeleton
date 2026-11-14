'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { h, load, render, text } = require('./harness.cjs');
const Q = load('src/skeletonForge/questionnaire.ts');
const Flow = load('src/skeletonForge/components/QuestionnaireFlow.tsx').default;

test('current game creator renders opt-in historical seven-stage conductor', () => {
  const markup = render(h(Flow, {
    state: { ...Q.INITIAL_STATE, step: 'options' },
    dispatch: () => {}, beats: Q.FALLBACK_BEATS, onForge: () => {},
  }));
  assert.match(markup, /data-testid="q-conductor-preview"/);
  assert.match(markup, /data-testid="q-conductor-preview-toggle"/);
  assert.match(text(markup), /historical seven-stage conductor preview/);
});

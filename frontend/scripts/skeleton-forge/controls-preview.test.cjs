'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { h, load, render, text } = require('./harness.cjs');
const Q = load('src/skeletonForge/questionnaire.ts');
const Flow = load('src/skeletonForge/components/QuestionnaireFlow.tsx').default;

test('selected genre shows an opt-in semantic controls inspector', () => {
  const state = Q.questionnaireReducer(Q.INITIAL_STATE, {
    type: 'setBrief', facet: 'genre', value: 'arena-shooter',
  });
  const markup = render(h(Flow, {
    state: { ...state, step: 'brief' },
    dispatch: () => {}, beats: Q.FALLBACK_BEATS, onForge: () => {},
  }));
  assert.match(markup, /data-testid="q-genre-control-preview"/);
  assert.match(markup, /data-testid="q-genre-controls-toggle"/);
  assert.match(text(markup), /keyboard, gamepad and touch controls/);
});

test('unselected genre does not fetch or show controls', () => {
  const markup = render(h(Flow, {
    state: { ...Q.INITIAL_STATE, step: 'brief' },
    dispatch: () => {}, beats: Q.FALLBACK_BEATS, onForge: () => {},
  }));
  assert.doesNotMatch(markup, /data-testid="q-genre-control-preview"/);
});

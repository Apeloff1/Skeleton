'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { h, load, render, text } = require('./harness.cjs');
const Q = load('src/skeletonForge/questionnaire.ts');
const Flow = load('src/skeletonForge/components/QuestionnaireFlow.tsx').default;
const Catalog = load('src/skeletonForge/genreCatalog.ts');

function reduce(...actions) {
  return actions.reduce(Q.questionnaireReducer, Q.INITIAL_STATE);
}
function screen(state) {
  return render(h(Flow, { state, dispatch: () => {}, beats: Q.FALLBACK_BEATS, onForge: () => {} }));
}

test('158-choice creator genre, design knobs and native quest compose one bounded request', () => {
  assert.equal(Catalog.GENRE_CHOICES.length, 158);
  const state = reduce(
    { type: 'setVision', vision: 'A coastal colony with autonomous harbor crews' },
    { type: 'setBrief', facet: 'genre', value: 'colony-sim' },
    { type: 'setAxis', axis: 'risk', value: 0.81 },
    { type: 'setAxis', axis: 'tempo', value: 0.23 },
    { type: 'setQuestEnabled', value: true },
    { type: 'setQuestLength', value: 6 },
  );
  const request = Q.buildRunRequest(state);
  assert.equal(request.answers.genre, 'colony-sim');
  assert.deepEqual(request.operator_axes, { risk: 0.81, tempo: 0.23 });
  assert.equal(request.quest_content, true);
  assert.equal(request.quest_length, 6);
  const review = text(screen({ ...state, step: 'review' }));
  assert.match(review, /Design tuning Risk: 81%/);
  assert.match(review, /Native quest 6 room-entry objectives/);
});

test('legacy 67-specialty selector survives cross-system quest and instrument composition', () => {
  const state = reduce(
    { type: 'setVision', vision: 'A cooperative orbital encounter' },
    { type: 'setGalaxyGenre', genre: 'fps' },
    { type: 'setAxis', axis: 'agency', value: 0.66 },
    { type: 'setQuestEnabled', value: true },
  );
  const request = Q.buildRunRequest(state);
  assert.equal(request.answers.genre, 'fps');
  assert.match(request.vision, /Specialized genre:/);
  assert.deepEqual(request.operator_axes, { agency: 0.66 });
  assert.equal(request.quest_length, 3);
  assert.match(text(screen({ ...state, step: 'review' })), /Specialized genre/);
});

test('JSON target suppresses only native quest, keeping genre and authored design knobs', () => {
  const state = reduce(
    { type: 'setBrief', facet: 'genre', value: 'farming-sim' },
    { type: 'setAxis', axis: 'scarcity', value: 0.19 },
    { type: 'setQuestEnabled', value: true },
    { type: 'setOption', key: 'target', value: 'json' },
  );
  const request = Q.buildRunRequest(state);
  assert.equal(request.target, 'json');
  assert.equal(request.answers.genre, 'farming-sim');
  assert.deepEqual(request.operator_axes, { scarcity: 0.19 });
  assert.equal(request.quest_content, undefined);
  assert.equal(request.quest_length, undefined);
  assert.match(text(screen({ ...state, step: 'review' })), /Native room quests are disabled/);
});

test('no opt-ins keep baseline request contract byte-compatible', () => {
  assert.deepEqual(Q.buildRunRequest(Q.INITIAL_STATE), {
    vision: '', era: null, archetype: 'auto', target: 'godot',
    generation: null, answers: {},
  });
});

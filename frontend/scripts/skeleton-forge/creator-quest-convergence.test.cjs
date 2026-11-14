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

test('native scene opt-in explains rendered goals and touch controls, without overclaiming 158 engines', () => {
  const state = reduce(
    { type: 'setVision', vision: 'A tactile original action game' },
    { type: 'setPlayableEnabled', value: true },
  );
  const ui = text(screen({ ...state, step: 'options' }));
  assert.match(ui, /draw visible objectives, live progress indicators/);
  assert.match(ui, /touch\/keyboard directional controller/);
  assert.match(ui, /three independent playable scenes/);
  assert.match(ui, /not a claim of 158 gameplay engines/);
});

test('native playable sidecar and room quest compose in the same Godot source request', () => {
  const state = reduce(
    { type: 'setVision', vision: 'An original planetary supply-chain escape game' },
    { type: 'setBrief', facet: 'genre', value: 'automation' },
    { type: 'setOption', key: 'archetype', value: 'pipeline' },
    { type: 'setAxis', axis: 'risk', value: 0.4 },
    { type: 'setPlayableEnabled', value: true },
    { type: 'setQuestEnabled', value: true },
    { type: 'setQuestLength', value: 7 },
  );
  const request = Q.buildRunRequest(state);
  assert.equal(request.playable_content, true);
  assert.equal(request.quest_content, true);
  assert.equal(request.quest_length, 7);
  assert.deepEqual(request.operator_axes, { risk: 0.4 });
  assert.equal(request.archetype, 'pipeline');
  const review = text(screen({ ...state, step: 'review' }));
  assert.match(review, /Playable scene Godot pipeline prototype/);
  assert.match(review, /Native quest 7 room-entry objectives/);
});

test('JSON blueprint never implicitly enables playable Godot, preserving authorship for later', () => {
  const state = reduce(
    { type: 'setVision', vision: 'A local puzzle-maker' },
    { type: 'setPlayableEnabled', value: true },
    { type: 'setQuestEnabled', value: true },
    { type: 'setOption', key: 'target', value: 'json' },
  );
  const req = Q.buildRunRequest(state);
  assert.equal(req.target, 'json');
  assert.equal(req.playable_content, undefined);
  assert.equal(req.quest_content, undefined);
  assert.equal(state.playable.enabled, true);
  assert.match(text(screen({ ...state, step: 'review' })), /Playable sidecar scenes require Godot output/);
  assert.deepEqual(Q.buildRunRequest(Q.questionnaireReducer(state, {
    type: 'setPlayableEnabled', value: false,
  })).playable_content, undefined);
});

test('required Godot qualification composes independently with playable scene, quest and axes', () => {
  const state = reduce(
    { type: 'setVision', vision: 'An original clockwork extraction game' },
    { type: 'setPlayableEnabled', value: true },
    { type: 'setQuestEnabled', value: true },
    { type: 'setPlaytestMode', value: 'require' },
    { type: 'setAxis', axis: 'risk', value: 0.5 },
  );
  const req = Q.buildRunRequest(state);
  assert.equal(req.target, 'godot');
  assert.equal(req.playtest, 'require');
  assert.equal(req.playable_content, true);
  assert.equal(req.quest_content, true);
  assert.deepEqual(req.operator_axes, { risk: 0.5 });
  assert.match(text(screen({ ...state, step: 'options' })), /Godot headless playtest/);
  assert.match(text(screen({ ...state, step: 'review' })), /Headless playtest Required/);
  assert.match(text(screen({ ...state, step: 'review' })), /main-world boot and playable scene completion/);
});

test('JSON export preserves authoring preferences but never requests a Godot playtest', () => {
  const state = reduce(
    { type: 'setVision', vision: 'An original printable game blueprint' },
    { type: 'setPlayableEnabled', value: true },
    { type: 'setQuestEnabled', value: true },
    { type: 'setPlaytestMode', value: 'auto' },
    { type: 'setOption', key: 'target', value: 'json' },
  );
  const request = Q.buildRunRequest(state);
  assert.equal(request.target, 'json');
  assert.equal(request.playtest, undefined);
  assert.equal(request.playable_content, undefined);
  assert.equal(request.quest_content, undefined);
  assert.match(text(screen({ ...state, step: 'review' })), /Headless Godot qualification is disabled/);
  assert.equal(state.playtest, 'auto');
});

test('no opt-ins keep baseline request contract byte-compatible', () => {
  assert.deepEqual(Q.buildRunRequest(Q.INITIAL_STATE), {
    vision: '', era: null, archetype: 'auto', target: 'godot',
    generation: null, answers: {},
  });
});

test('creator explicitly distinguishes mechanically applied sliders from design-only tensor controls', () => {
  const state = reduce(
    { type: 'setPlayableEnabled', value: true },
    { type: 'setAxis', axis: 'tempo', value: 0.9 },
    { type: 'setAxis', axis: 'intimacy', value: 0.2 },
  );
  const req = Q.buildRunRequest(state);
  assert.deepEqual(req.operator_axes, { tempo: 0.9, intimacy: 0.2 });
  const html = text(screen({ ...state, step: 'options' }));
  assert.match(html, /sliders now modify the underlying generated Godot movement/);
  assert.match(html, /other sliders currently tune the design tensor/);
});

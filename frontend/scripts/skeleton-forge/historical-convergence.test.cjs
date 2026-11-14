'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { h, load, render, text } = require('./harness.cjs');

const Q = load('src/skeletonForge/questionnaire.ts');
const G = load('src/skeletonForge/galaxyHandoff.ts');
const Flow = load('src/skeletonForge/components/QuestionnaireFlow.tsx').default;

function profile() {
  const payload = {
    title: 'Silver Lattice',
    genre: 'rpg',
    game_vision: 'A sprawling original quest world',
    game_pace: 'action_packed',
    difficulty_curve: 'adaptive',
    narrative_branching: 5,
    juice: 8,
    narrative_phases: { prelude: { count: 4, secrets: 3 } },
    extra_params: { quest_variety: 20 },
    style_params: { graphic_style: 'pixel_art' },
  };
  for (const name of G.MATRIX_FIELDS) payload[name] = { kickoff: { count: 5 } };
  return G.normaliseGalaxyProfile(payload);
}

test('full Galaxy draft, ten-axis cockpit, native quests reach a single request', () => {
  let state = Q.questionnaireReducer(Q.INITIAL_STATE, {
    type: 'importGalaxy', profile: profile(),
  });
  state = Q.questionnaireReducer(state, { type: 'setAxis', axis: 'risk', value: 0.85 });
  state = Q.questionnaireReducer(state, { type: 'setQuestEnabled', value: true });
  state = Q.questionnaireReducer(state, { type: 'setQuestLength', value: 8 });
  const wire = Q.buildRunRequest(state);
  assert.equal(wire.target, 'godot');
  assert.equal(wire.quest_content, true);
  assert.equal(wire.quest_length, 8);
  assert.equal(wire.operator_axes.risk, 0.85);
  assert.equal(wire.operator_axes.tempo, 0.8);
  assert.equal(wire.galaxy_profile.schema, G.GALAXY_PROFILE_SCHEMA);
  assert.equal(wire.galaxy_profile.config.extra_params.quest_variety, 20);
  assert.equal(wire.answers.genre, 'rpg');
});

test('the canonical options page preserves all three recovery control surfaces', () => {
  let state = Q.questionnaireReducer(Q.INITIAL_STATE, {
    type: 'importGalaxy', profile: profile(),
  });
  state = Q.questionnaireReducer(state, { type: 'setQuestEnabled', value: true });
  const html = render(h(Flow, {
    state: { ...state, step: 'options' },
    dispatch: () => {}, beats: Q.FALLBACK_BEATS, onForge: () => {},
    onOpenGalaxyStudio: () => {},
  }));
  assert.match(html, /data-testid="q-native-quest-controls"/);
  assert.match(html, /data-testid="q-galaxy-genres-toggle"/);
  assert.match(html, /data-testid="q-design-instruments-toggle"/);
  assert.match(html, /data-testid="q-open-galaxy-studio"/);
  assert.match(text(html), /complete Galaxy questionnaire is attached/);
  assert.match(html, /data-testid="q-native-quest-length"/);
  assert.match(text(html), /Quest objective count: 3/);
});

test('JSON export never advertises playable Godot quests yet retains Galaxy design', () => {
  let state = Q.questionnaireReducer(Q.INITIAL_STATE, {
    type: 'importGalaxy', profile: profile(),
  });
  state = Q.questionnaireReducer(state, { type: 'setQuestEnabled', value: true });
  state = Q.questionnaireReducer(state, {
    type: 'setOption', key: 'target', value: 'json',
  });
  const wire = Q.buildRunRequest(state);
  assert.equal(wire.galaxy_profile.schema, G.GALAXY_PROFILE_SCHEMA);
  assert.equal(wire.quest_content, undefined);
  assert.equal(wire.quest_length, undefined);
  const html = render(h(Flow, {
    state: { ...state, step: 'review' },
    dispatch: () => {}, beats: Q.FALLBACK_BEATS, onForge: () => {},
  }));
  assert.match(text(html), /Native room quests are disabled for JSON blueprint output/);
  assert.match(text(html), /Full 14 matrices/);
});

test('legacy source-compatible mode serializes no new params until opted in', () => {
  const wire = Q.buildRunRequest(Q.INITIAL_STATE);
  assert.equal(wire.galaxy_profile, undefined);
  assert.equal(wire.operator_axes, undefined);
  assert.equal(wire.quest_content, undefined);
  assert.equal(wire.quest_length, undefined);
});

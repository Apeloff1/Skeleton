'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { h, load, render, text, ROOT } = require('./harness.cjs');
const G = load('src/skeletonForge/galaxyHandoff.ts');
const Q = load('src/skeletonForge/questionnaire.ts');
const Flow = load('src/skeletonForge/components/QuestionnaireFlow.tsx').default;

function payload(overrides = {}) {
  const p = {
    title: 'North Star',
    genre: 'racing',
    game_vision: 'Build an original old-school arcade racing game.',
    game_pace: 'breakneck', difficulty_curve: 'punishing',
    narrative_branching: 3, juice: 8,
    extra_params: { music_variety: 9, motion_sickness_options: 10 },
    style_params: { graphic_style: 'pixel_art' },
    narrative_phases: { prelude: { count: 5, secrets: 3 } },
    subgenre: undefined,
    ...overrides,
  };
  for (const key of G.MATRIX_FIELDS) p[key] = { kickoff: { count: 5, complexity: 8 } };
  return p;
}

test('Galaxy handoff exactly inventories every historical matrix', () => {
  assert.deepEqual(G.MATRIX_FIELDS, [
    'mechanics_matrix', 'world_matrix', 'art_matrix', 'audio_matrix',
    'tech_matrix', 'monetisation_matrix', 'qa_matrix', 'agent_matrix',
    'vector_db_matrix', 'plagiarism_matrix', 'rdbms_matrix', 'styles_matrix',
    'mutation_matrix', 'unique_flair_matrix',
  ]);
  const source = fs.readFileSync(path.join(ROOT, 'src/features/GalaxyStudioFactory/GalaxyStudioFactoryModal.tsx'), 'utf8');
  for (const field of G.MATRIX_FIELDS) {
    assert.match(source, new RegExp('\\b' + field + ':\\s*[a-zA-Z]+Matrix'));
  }
  assert.match(source, /makeGalaxyBuildPayload\(selectedGenre\)/);
  assert.match(source, /prepareGalaxyHandoff\(makeGalaxyBuildPayload\(selectedGenre\)\)/);
  assert.match(source, /galaxy-send-full-design-to-gameforge/);
});

test('single-use per-app navigation preserves exact complete authoring snapshot', () => {
  const p = payload();
  const id = G.prepareGalaxyHandoff(p, 1000);
  p.mechanics_matrix.kickoff.count = 999;
  const read = G.consumeGalaxyHandoff(id, 1001);
  assert.ok(read && read.schema === G.GALAXY_PROFILE_SCHEMA);
  assert.equal(read.config.mechanics_matrix.kickoff.count, 5);
  assert.equal(read.config.extra_params.music_variety, 9);
  assert.equal(read.config.narrative_phases.prelude.secrets, 3);
  assert.equal(read.config.style_params.graphic_style, 'pixel_art');
  assert.equal(G.consumeGalaxyHandoff(id, 1002), null);
});

test('unknown, expired and replaced handoffs do not expose design data', () => {
  const a = G.prepareGalaxyHandoff(payload(), 1234);
  assert.equal(G.consumeGalaxyHandoff('bad', 1235), null);
  const b = G.prepareGalaxyHandoff(payload({ title: 'Second' }), 1236);
  assert.equal(G.consumeGalaxyHandoff(a, 1237), null);
  assert.equal(G.consumeGalaxyHandoff(b, 1237).config.title, 'Second');
  const expired = G.prepareGalaxyHandoff(payload(), 1234);
  assert.equal(G.consumeGalaxyHandoff(expired, 1234 + G.PROFILE_TTL_MS + 1), null);
});

test('client profile rejects nonfinite, untrusted, oversized or incomplete data', () => {
  assert.throws(() => G.normaliseGalaxyProfile(payload({ title: '' })));
  assert.throws(() => G.normaliseGalaxyProfile(payload({ juice: Infinity })));
  assert.throws(() => G.normaliseGalaxyProfile(payload({ extra_params: { x: NaN } })));
  assert.throws(() => G.normaliseGalaxyProfile(payload({ game_vision: 'z'.repeat(12_001) })));
  const missingMatrix = payload();
  missingMatrix.styles_matrix = null;
  assert.throws(() => G.normaliseGalaxyProfile(missingMatrix));
  assert.throws(() => G.normaliseGalaxyProfile(payload({ extra_params: { constructor: 3 } })));
  assert.throws(() => G.normaliseGalaxyProfile(payload({ narrative_phases: { prelude: [undefined] } })));
});

test('complete profile enters canonical run, while axis meanings remain explicit', () => {
  const profile = G.normaliseGalaxyProfile(payload());
  const prefill = G.galaxyPrefill(profile);
  assert.equal(prefill.genre, 'racing');
  assert.equal(prefill.mappedGenre, 'simulation');
  assert.deepEqual(prefill.axes, { tempo: 1, risk: 0.95, agency: 0.43, spectacle: 0.8 });
  assert.match(prefill.vision, /North Star/);
  let state = Q.questionnaireReducer(Q.INITIAL_STATE, { type: 'importGalaxy', profile });
  assert.equal(state.step, 'options');
  assert.equal(state.brief.genre, 'simulation');
  assert.equal(state.galaxyGenre, 'racing');
  const sent = Q.buildRunRequest(state);
  assert.equal(sent.answers.genre, 'simulation');
  assert.equal(sent.galaxy_profile.config.mechanics_matrix.kickoff.complexity, 8);
  assert.deepEqual(sent.operator_axes, prefill.axes);
  state = Q.questionnaireReducer(state, { type: 'clearGalaxyProfile' });
  assert.equal(Q.buildRunRequest(state).galaxy_profile, undefined);
});

test('Forge review shows authoritative full imported profile and explicit detach', () => {
  const profile = G.normaliseGalaxyProfile(payload());
  let state = Q.questionnaireReducer(Q.INITIAL_STATE, { type: 'importGalaxy', profile });
  state = Q.questionnaireReducer(state, { type: 'goto', step: 'review' });
  const view = render(h(Flow, { state, dispatch: () => {}, beats: Q.FALLBACK_BEATS, onForge: () => {} }));
  assert.match(text(view), /Full 14 matrices/);
  assert.match(view, /q-detach-galaxy-profile/);
  const opt = render(h(Flow, { state: { ...state, step: 'options' },
    dispatch: () => {}, beats: Q.FALLBACK_BEATS, onForge: () => {} }));
  assert.match(text(opt), /complete Galaxy questionnaire is attached/);
});

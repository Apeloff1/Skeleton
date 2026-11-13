'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { h, load, render, text } = require('./harness.cjs');
const Q = load('src/skeletonForge/questionnaire.ts');
const R = load('src/skeletonForge/run.ts');
const Flow = load('src/skeletonForge/components/QuestionnaireFlow.tsx').default;
const Panel = load('src/skeletonForge/components/ForgeRunPanel.tsx').default;

test('native validation is off by default and JSON output cannot demand Godot', () => {
  assert.equal(Q.buildRunRequest(Q.INITIAL_STATE).playtest, undefined);
  const json = Q.questionnaireReducer(Q.INITIAL_STATE, { type: 'setOption', key: 'target', value: 'json' });
  assert.strictEqual(Q.questionnaireReducer(json, { type: 'setPlaytestMode', value: 'require' }), json);
  assert.equal(Q.buildRunRequest({ ...json, playtest: 'require' }).playtest, undefined);
});
test('native auto and require selections flow to exact API build request', () => {
  for (const mode of ['auto', 'require']) {
    let state = Q.questionnaireReducer(Q.INITIAL_STATE, { type: 'setPlaytestMode', value: mode });
    state = Q.questionnaireReducer(state, { type: 'setPlayableEnabled', value: true });
    state = Q.questionnaireReducer(state, { type: 'setPlayableMode', value: 'crafting' });
    const request = Q.buildRunRequest(state);
    assert.equal(request.playtest, mode);
    assert.equal(request.playable_content, true);
    assert.equal(request.playable_archetype, 'crafting');
  }
});
test('native source checks and opt-in modes appear in options UI', () => {
  const html = render(h(Flow, {
    state: { ...Q.INITIAL_STATE, step: 'options' },
    dispatch: () => {}, beats: Q.FALLBACK_BEATS, onForge: () => {},
  }));
  for (const id of ['off', 'auto', 'require']) {
    assert.match(html, new RegExp('data-testid="q-native-playtest-' + id + '"'));
  }
  assert.match(text(html), /independently of the main world/);
});
test('conflicting Godot status flags never produce green main-world evidence', () => {
  for (const p of [{ status: 'passed', passed: false }, { status: 'failed', passed: true }]) {
    assert.equal(R.playtestView({ playtest: p }).tone, 'bad');
  }
  assert.equal(R.playtestView({ playtest: { status: 'passed', passed: true, verified: false } }).tone, 'warn');
  assert.equal(R.playtestView({ playtest: { status: 'passed', passed: true, verified: true } }).tone, 'ok');
});
test('scene proof needs exact completion status and admitted Godot provenance', () => {
  const base = { forge: { playable_archetype: 'puzzle' } };
  assert.equal(R.playableSceneView(base).state, 'off');
  for (const p of [{ status: 'failed', passed: true }, { status: 'passed', passed: false }]) {
    assert.equal(R.playableSceneView({ ...base, playable_scene_playtest: p }).tone, 'bad');
  }
  assert.equal(R.playableSceneView({ ...base, playable_scene_playtest: { status: 'passed', passed: true, verified: false } }).tone, 'warn');
  assert.equal(R.playableSceneView({ ...base, playable_scene_playtest: { status: 'passed', passed: true, verified: true } }).tone, 'ok');
});
test('run view warns when native gameplay succeeds on unknown engine binary', () => {
  const payload = {
    succeeded: true,
    run: { run_id: 'source-proof', succeeded: true, stages: [] },
    forge: { playable_archetype: 'puzzle', playable_launcher: 'scripts/autoloads/playable_hub.gd' },
    playtest: { status: 'passed', passed: true, verified: false },
    playable_scene_playtest: {
      status: 'passed', passed: true, verified: false,
      scene: 'res://scenes/archetypes/puzzle/main.tscn',
    },
  };
  const html = render(h(Panel, { phase: 'success', payload, startedAt: 1, finishedAt: 2001 }));
  assert.match(html, /data-testid="run-native-playable-scene"/);
  assert.match(html, /data-testid="run-native-binary-unverified"/);
  assert.match(text(html), /puzzle/);
  assert.match(text(html), /engine integrity unverified/);
});

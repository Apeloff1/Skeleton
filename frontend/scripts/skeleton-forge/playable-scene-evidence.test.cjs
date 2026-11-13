'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { h, load, render, text } = require('./harness.cjs');
const Run = load('src/skeletonForge/run.ts');
const Panel = load('src/skeletonForge/components/ForgeRunPanel.tsx').default;

function payload(sceneReport, mainReport = null) {
  return {
    succeeded: true, era: 'extraction_now',
    run: { run_id: 'hermetic-preview', succeeded: true, stages: [] },
    forge: { file_count: 11, playable_archetype: 'pipeline' },
    playtest: mainReport,
    playable_scene_playtest: sceneReport,
    native_quest: { steps: 4, sealed: true },
  };
}

test('main-world success cannot substitute for absent playable sidecar proof', () => {
  const p = payload(null, { status: 'passed', passed: true });
  assert.equal(Run.playtestView(p).state, 'passed');
  assert.deepEqual(Run.playableSceneView(p), {
    state: 'off', tone: 'idle', label: 'Playable scene not dynamically tested',
  });
  assert.equal(Run.playableSceneView({ ...p, forge: {} }), null);
});

test('both status and passed flag are required before any runtime badge is green', () => {
  for (const p of [
    { status: 'passed', passed: false },
    { status: 'failed', passed: true },
    { status: 'unavailable', passed: true },
  ]) {
    assert.notEqual(Run.playableSceneView(payload(p)).tone, 'ok');
    assert.notEqual(Run.playtestView(payload(null, p)).tone, 'ok');
  }
  const confirmed = payload({
    status: 'passed', passed: true, scene: 'scenes/archetypes/pipeline/main.tscn',
  });
  assert.equal(Run.playableSceneView(confirmed).state, 'passed');
  assert.equal(Run.playableSceneView(confirmed).tone, 'ok');
  assert.equal(Run.playtestView(payload(null, { status: 'passed', passed: true })).tone, 'ok');
});

test('unavailable Godot is warning and failures cannot be presented as valid gameplay', () => {
  const missing = Run.playableSceneView(payload({
    status: 'unavailable', passed: false, reason: 'missing-godot-binary',
  }));
  assert.equal(missing.state, 'unavailable');
  assert.equal(missing.tone, 'warn');
  const failed = Run.playableSceneView(payload({
    status: 'failed', passed: false, errors: ['frame budget exhausted'],
  }));
  assert.equal(failed.state, 'failed');
  assert.equal(failed.tone, 'bad');
});

test('result panel visibly distinguishes world boot, sidecar completion and original quest receipt', () => {
  const p = payload(
    { status: 'passed', passed: true, scene: 'scenes/archetypes/pipeline/main.tscn' },
    { status: 'passed', passed: true },
  );
  const screen = text(render(h(Panel, {
    phase: 'done', payload: p, now: 100, startedAt: 0, finishedAt: 100,
  })));
  assert.match(screen, /Headless Godot playtest passed/);
  assert.match(screen, /Independent playable scene/);
  assert.match(screen, /Playable pipeline scene completed in Godot/);
  assert.match(screen, /4 room objectives/);
  assert.match(screen, /source sealed/);
  assert.match(screen, /Godot binary has not been verified against admitted release provenance/);
  assert.match(screen, /Godot binary's release provenance is unverified/);
});

test('an admitted Godot binary does not emit provenance warning after separate successful boots', () => {
  const passed = { status: 'passed', passed: true, verified: true };
  const result = payload({ ...passed, scene: 'scenes/archetypes/pipeline/main.tscn' }, passed);
  const screen = text(render(h(Panel, { phase: 'done', payload: result })));
  assert.match(screen, /Playable pipeline scene completed in Godot/);
  assert.doesNotMatch(screen, /binary's release provenance is unverified/);
  assert.doesNotMatch(screen, /binary has not been verified/);
});

test('missing sidecar runtime proof stays explicitly unverified in finished panel', () => {
  const screen = text(render(h(Panel, { phase: 'done', payload: payload(null) })));
  assert.match(screen, /Playable scene not dynamically tested/);
  assert.doesNotMatch(screen, /Playable pipeline scene completed in Godot/);
});

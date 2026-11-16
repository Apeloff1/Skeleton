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
  assert.equal(Run.playableSceneView(confirmed).tone, 'warn');
  assert.equal(Run.playtestView(payload(null, { status: 'passed', passed: true })).tone, 'warn');
  assert.equal(Run.playableSceneView(payload({ status: 'passed', passed: true, verified: true, scene: 'scenes/archetypes/pipeline/main.tscn' })).tone, 'ok');
  assert.equal(Run.playtestView(payload(null, { status: 'passed', passed: true, verified: true })).tone, 'ok');
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

test('generated source-sealed in-game gateway is separately visible from engine qualifications', () => {
  const basic = payload(null, null);
  const sealed = {
    ...basic,
    playable_portal: {
      schema: 'skeleton.forge.playable_portal.v1',
      scene: 'scenes/archetypes/pipeline/main.tscn',
      source_sha256: 'a'.repeat(64),
      return_supported: true,
      sealed: true,
    },
  };
  const body = text(render(h(Panel, { phase: 'done', payload: sealed })));
  assert.match(body, /In-game playable gateway/);
  assert.match(body, /Source sealed · launch \+ return/);
  assert.match(body, /Playable scene not dynamically tested/);
  assert.doesNotMatch(body, /gateway was generated but its project/);

  const unsealed = {
    ...sealed,
    playable_portal: { ...sealed.playable_portal, sealed: false },
  };
  const unsafe = text(render(h(Panel, { phase: 'done', payload: unsealed })));
  assert.match(unsafe, /Not source sealed/);
  assert.match(unsafe, /gateway was generated but its project\/source receipt is not sealed/);
});

test('missing sidecar runtime proof stays explicitly unverified in finished panel', () => {
  const screen = text(render(h(Panel, { phase: 'done', payload: payload(null) })));
  assert.match(screen, /Playable scene not dynamically tested/);
  assert.doesNotMatch(screen, /Playable pipeline scene completed in Godot/);
});

test('mechanical tuning receipt identifies only axes actually implemented in Godot source', () => {
  const x = payload(null);
  const tuned = {
    ...x,
    playable_mechanics: {
      schema: 'skeleton.forge.playable_mechanics.v1',
      archetype: 'pipeline',
      source_verified: true,
      applied_axes: { tempo: 0.8, grind: 0.75, risk: 0.3 },
    },
  };
  const html = text(render(h(Panel, { phase: 'done', payload: tuned })));
  assert.match(html, /Native mechanics tuning/);
  assert.match(html, /tempo 80%/);
  assert.match(html, /grind 75%/);
  assert.match(html, /risk 30%/);
  const creativeOnly = text(render(h(Panel, { phase: 'done', payload: {
    ...tuned, playable_mechanics: {
      ...tuned.playable_mechanics, applied_axes: {},
    },
  } })));
  assert.match(creativeOnly, /Original default mechanics/);
  const unverified = text(render(h(Panel, { phase: 'done', payload: {
    ...tuned, playable_mechanics: { ...tuned.playable_mechanics, source_verified: false },
  } })));
  assert.match(unverified, /Source tuning not verified/);
});


function nativeTuningPayload() {
  const p = payload(null);
  const native = {
    'scenes/archetypes/pipeline/main.tscn': 'a'.repeat(64),
    'scripts/archetypes/pipeline/player_controller.gd': 'b'.repeat(64),
    'scripts/archetypes/pipeline/core_loop.gd': 'c'.repeat(64),
  };
  return { ...p, playable_mechanics: {
    archetype: 'pipeline', source_verified: true, applied_axes: { grind: 1 },
  }, playable_tuning: {
    schema: 'skeleton.gameforge.playable_tuning.v1', mode: 'pipeline',
    axes: { grind: 1, authorial: 0.5 }, applied: { 'pipeline.shipment_quota': 8 },
    mapped_axes: ['grind'], unmapped_axes: ['authorial'],
  }, galaxy_playable_controls: {
    schema: 'skeleton.gameforge.galaxy_playable_controls.v1', mode: 'pipeline',
    profile_sha256: 'd'.repeat(64), active_matrix_dials: 5, mapped_matrix_dials: 1,
    unmapped_matrix_dials: 4, source_verified: true, native_execution_qualified: false,
    effective_axes: { grind: 1, authorial: 0.5 }, native_sources: native,
    tuning_receipt_sha256: 'e'.repeat(64),
    axes: [{ axis: 'grind', requested: 0.8, effective: 1, authority: 'forge_override',
      sources: [{ path: 'mechanics_matrix.building.count', value: 800 }] }],
  }, source_manifest: { files: { ...native, 'data/playable_tuning.json': 'e'.repeat(64) } } };
}
test('native effect panel shows concrete values and Galaxy override authority', () => {
  const result = nativeTuningPayload();
  const screen = text(render(h(Panel, { phase: 'done', payload: result })));
  assert.match(screen, /Generated gameplay controls/);
  assert.match(screen, /Shipment quota/);
  assert.match(screen, /Design only: authorial/);
  assert.match(screen, /1 \/ 5 active dials connected/);
  assert.match(screen, /grind · Forge override/);
  assert.match(screen, /80% → 100%/);
  assert.match(screen, /not device or player acceptance/);
});
for (const [name, change] of [
  ['foreign mode', p => p.playable_tuning.mode = 'racing'],
  ['unknown effect', p => p.playable_tuning.applied['pipeline.fake'] = 100],
  ['overlapping axes', p => p.playable_tuning.unmapped_axes.push('grind')],
  ['inconsistent mechanics', p => p.playable_mechanics.applied_axes.grind = 0],
  ['foreign digest', p => p.source_manifest.files['data/playable_tuning.json'] = 'f'.repeat(64)],
  ['invented acceptance', p => p.galaxy_playable_controls.native_execution_qualified = true],
  ['inconsistent counts', p => p.galaxy_playable_controls.unmapped_matrix_dials = 5],
  ['foreign vote', p => p.galaxy_playable_controls.axes[0].sources[0].path = '../private'],
]) {
  test('native control panel refuses ' + name, () => {
    const p = nativeTuningPayload(); change(p);
    const screen = text(render(h(Panel, { phase: 'done', payload: p })));
    assert.match(screen, /Native control evidence is missing or inconsistent/);
    assert.doesNotMatch(screen, /Shipment quota/);
    assert.doesNotMatch(screen, /Forge override/);
  });
}

test('wrong native scene never inherits a successful engine badge', () => {
  const report = { status: 'passed', passed: true, verified: true, scene: 'scenes/archetypes/racing/main.tscn' };
  assert.equal(Run.playableSceneView(payload(report)).state, 'failed');
  assert.equal(Run.playableSceneView(payload({ ...report, scene: undefined })).tone, 'warn');
});

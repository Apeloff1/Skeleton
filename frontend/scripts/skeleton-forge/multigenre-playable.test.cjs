'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { h, load, render, text } = require('./harness.cjs');

const Q = load('src/skeletonForge/questionnaire.ts');
const Flow = load('src/skeletonForge/components/QuestionnaireFlow.tsx').default;
const MODES = [
  'extraction', 'combat_loop', 'pipeline', 'puzzle',
  'racing', 'survival', 'stealth', 'crafting',
];

function reducer(...acts) {
  return acts.reduce(Q.questionnaireReducer, Q.INITIAL_STATE);
}
function display(state, step = 'options') {
  return render(h(Flow, { state: { ...state, step },
    beats: Q.FALLBACK_BEATS, dispatch: () => {}, onForge: () => {} }));
}

test('historical creator offers all eight actual native mini-games, not 69 fictional ones', () => {
  assert.deepEqual(Q.PLAYABLE_SLICES.map((s) => s.id), MODES);
  assert.equal(new Set(Q.PLAYABLE_SLICES.map((s) => s.id)).size, 8);
  const html = display(Q.INITIAL_STATE);
  assert.match(html, /data-testid="q-playable-slice-options"/);
  assert.match(text(html), /eight implemented prototypes/);
  assert.match(text(html), /not mean all 69 catalog genres/);
});

test('default request unchanged until users explicitly opt in to playable content', () => {
  const wire = Q.buildRunRequest(Q.INITIAL_STATE);
  assert.equal(wire.playable_content, undefined);
  assert.equal(wire.playable_archetype, undefined);
  assert.equal(wire.playable_main_scene, undefined);
});

test('each playable archetype reaches one canonical run request and is selectable as startup', () => {
  for (const mode of MODES) {
    const state = reducer(
      { type: 'setPlayableEnabled', value: true },
      { type: 'setPlayableMode', value: mode },
      { type: 'setPlayableMainScene', value: true },
    );
    const wire = Q.buildRunRequest(state);
    assert.equal(wire.playable_content, true);
    assert.equal(wire.playable_archetype, mode);
    assert.equal(wire.playable_main_scene, true);
  }
});

test('native room quests and playable mini-games can coexist without conflicting startup scenes', () => {
  let state = reducer(
    { type: 'setPlayableEnabled', value: true },
    { type: 'setPlayableMode', value: 'survival' },
    { type: 'setPlayableMainScene', value: true },
    { type: 'setQuestEnabled', value: true },
  );
  assert.equal(state.playable.launch, false);
  let req = Q.buildRunRequest(state);
  assert.equal(req.quest_content, true);
  assert.equal(req.playable_content, true);
  assert.equal(req.playable_archetype, 'survival');
  assert.equal(req.playable_main_scene, false);
  assert.equal(Q.questionnaireReducer(state, {
    type: 'setPlayableMainScene', value: true,
  }), state);
  assert.match(text(display(state)), /original Godot launch scene/);
});

test('JSON exports do not attach unusable native loops, and review explains why', () => {
  const state = reducer(
    { type: 'setPlayableEnabled', value: true },
    { type: 'setPlayableMode', value: 'racing' },
    { type: 'setOption', key: 'target', value: 'json' },
  );
  const req = Q.buildRunRequest(state);
  assert.equal(req.playable_content, undefined);
  assert.equal(req.playable_archetype, undefined);
  assert.equal(req.playable_main_scene, undefined);
  assert.match(text(display(state, 'review')), /Native playable mini-games require Godot output/);
});

test('unknown playable IDs are rejected without changing author intent', () => {
  let state = reducer(
    { type: 'setPlayableEnabled', value: true },
    { type: 'setPlayableMode', value: 'puzzle' },
  );
  assert.equal(Q.questionnaireReducer(state, {
    type: 'setPlayableMode', value: '__proto__',
  }), state);
  state = Q.questionnaireReducer(state, { type: 'setPlayableEnabled', value: false });
  assert.equal(Q.buildRunRequest(state).playable_content, undefined);
});

test('review distinguishes actual extra playable content from the starting scene', () => {
  const selected = reducer(
    { type: 'setPlayableEnabled', value: true },
    { type: 'setPlayableMode', value: 'crafting' },
  );
  assert.match(text(display(selected, 'review')), /Crafting Delivery.*additional scene/);
  const launched = Q.questionnaireReducer(selected, {
    type: 'setPlayableMainScene', value: true,
  });
  assert.match(text(display(launched, 'review')), /Crafting Delivery.*startup scene/);
});



test('including a bonus scene exposes an accessible in-game launcher option', () => {
  const state = reducer(
    { type: 'setPlayableEnabled', value: true },
    { type: 'setPlayableMode', value: 'puzzle' },
  );
  assert.match(text(display(state)), /Keep main world; add in-game switch button/);
  assert.match(text(display(state, 'review')), /Spatial Puzzle.*additional scene/);
});



test('historical genre hints are sparse, honest and never mutate intent automatically', () => {
  const H = load('src/skeletonForge/playableSuggestions.ts');
  assert.equal(H.suggestPlayableMode('racing').mode, 'racing');
  assert.equal(H.suggestPlayableMode('extraction_shooter').mode, 'extraction');
  assert.equal(H.suggestPlayableMode('tycoon').mode, 'pipeline');
  assert.equal(H.suggestPlayableMode('puzzle').mode, 'puzzle');
  assert.equal(H.suggestPlayableMode('rpg'), null, 'a full RPG cannot be faked as a mini-loop');
  assert.equal(H.suggestPlayableMode('platformer_2d'), null);
  assert.equal(H.suggestPlayableMode('__proto__'), null);
  let state = reducer(
    { type: 'setVision', vision: 'Original racing title' },
    { type: 'setGalaxyGenre', genre: 'racing' },
    { type: 'setPlayableEnabled', value: true },
  );
  assert.equal(Q.buildRunRequest(state).playable_archetype, 'extraction');
  const html = display(state);
  assert.match(html, /data-testid="q-playable-suggestion"/);
  assert.match(html, /data-testid="q-use-playable-suggestion"/);
  assert.match(text(html), /only a small prototype, not full specialized genre gameplay/);
  state = Q.questionnaireReducer(state, { type: 'setPlayableMode', value: 'racing' });
  assert.equal(Q.buildRunRequest(state).playable_archetype, 'racing');
});

test('unsupported Galaxy genres show no misleading playable recommendation', () => {
  const state = reducer(
    { type: 'setGalaxyGenre', genre: 'rpg' },
    { type: 'setPlayableEnabled', value: true },
  );
  assert.doesNotMatch(display(state), /data-testid="q-playable-suggestion"/);
});


test('creator explains exact authored cockpit effects for every supported mini-game', () => {
  for (const mode of MODES) {
    const state = reducer(
      { type: 'setPlayableEnabled', value: true },
      { type: 'setPlayableMode', value: mode },
    );
    const hints = Q.PLAYABLE_TUNING_EFFECTS[mode];
    assert.ok(hints && hints.includes('Tempo → movement speed'));
    const html = display(state);
    assert.match(html, /data-testid="q-playable-tuning-hint"/);
    assert.match(text(html), /Other design sliders remain in the full GameForge tensor/);
  }
  assert.deepEqual(Q.PLAYABLE_TUNING_EFFECTS.racing, [
    'Tempo → movement speed', 'Risk → checkpoint time limit',
    'Progression depth → race laps',
  ]);
  assert.deepEqual(Q.PLAYABLE_TUNING_EFFECTS.survival, [
    'Tempo → movement speed', 'Scarcity → hydration drain',
  ]);
});


test('creator discloses progression and mystery effects only where implemented', () => {
  assert.deepEqual(Q.PLAYABLE_TUNING_EFFECTS.puzzle, [
    'Tempo → movement speed', 'Mystery → switch hints',
  ]);
  assert.deepEqual(Q.PLAYABLE_TUNING_EFFECTS.stealth, [
    'Tempo → movement speed', 'Risk → guard detection radius',
    'Mystery → guard-zone visibility',
  ]);
  assert.deepEqual(Q.PLAYABLE_TUNING_EFFECTS.pipeline, [
    'Tempo → movement speed', 'Progression depth → shipment quota',
  ]);
  assert.deepEqual(Q.PLAYABLE_TUNING_EFFECTS.combat_loop, [
    'Tempo → movement speed', 'Lethality → starting health',
    'Progression depth → combat waves',
  ]);
  assert.deepEqual(Q.PLAYABLE_TUNING_EFFECTS.crafting, [
    'Tempo → movement speed',
  ]);
});

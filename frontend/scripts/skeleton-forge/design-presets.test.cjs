'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { h, load, render, text } = require('./harness.cjs');

const Q = load('src/skeletonForge/questionnaire.ts');
const P = load('src/skeletonForge/designPresets.ts');
const G = load('src/skeletonForge/galaxyHandoff.ts');
const Panel = load('src/skeletonForge/components/DesignPresetPanel.tsx').default;
const Flow = load('src/skeletonForge/components/QuestionnaireFlow.tsx').default;

function originalProfile() {
  const cfg = {
    title: 'Library Starfall',
    genre: 'racing',
    game_vision: 'An original multi-era campaign',
    game_pace: 'action_packed',
    difficulty_curve: 'adaptive',
    narrative_phases: { prelude: { count: 3, secrets: 8 } },
    extra_params: { quest_variety: 40 },
    style_params: { graphic_style: 'pixel_art' },
  };
  for (const field of G.MATRIX_FIELDS) cfg[field] = { kickoff: { count: 12, complexity: 4 } };
  return G.normaliseGalaxyProfile(cfg);
}

function filled() {
  let state = Q.questionnaireReducer(Q.INITIAL_STATE, {
    type: 'importGalaxy', profile: originalProfile(),
  });
  const actions = [
    { type: 'setBrief', facet: 'theme', value: 'cyberpunk' },
    { type: 'setBeat', beat: 'death', value: 'the_raid' },
    { type: 'setAxis', axis: 'risk', value: 0.8 },
    { type: 'setAxis', axis: 'grind', value: 0.65 },
    { type: 'setQuestEnabled', value: true },
    { type: 'setQuestLength', value: 8 },
    { type: 'setPlayableEnabled', value: true },
    { type: 'setPlayableMode', value: 'racing' },
  ];
  for (const action of actions) state = Q.questionnaireReducer(state, action);
  return state;
}

test('explicit preset retains full 14-matrix questionnaire, knobs, quest and mode', () => {
  const state = filled();
  const preset = P.makeDesignPreset('Starfall / racing', state, 1700000000123);
  assert.equal(preset.schema, P.DESIGN_PRESET_SCHEMA);
  assert.equal(preset.name, 'Starfall / racing');
  assert.equal(preset.updatedAt, 1700000000123);
  assert.equal(preset.state.step, 'options');
  assert.equal(preset.state.galaxyProfile.schema, G.GALAXY_PROFILE_SCHEMA);
  assert.equal(G.MATRIX_FIELDS.length, 14);
  assert.equal(preset.state.galaxyProfile.config.mechanics_matrix.kickoff.count, 12);
  assert.equal(preset.state.galaxyProfile.config.extra_params.quest_variety, 40);
  assert.deepEqual(Object.fromEntries(Object.entries(preset.state.instruments).sort()), {
    grind: 0.65, risk: 0.8, tempo: 0.8,
  });
  assert.deepEqual(preset.state.quest, { enabled: true, length: 8 });
  assert.deepEqual(preset.state.playable, { enabled: true, mode: 'racing', launch: false });
  const encoded = P.encodeDesignPresets([preset]);
  assert.equal(encoded, P.encodeDesignPresets(P.decodeDesignPresets(encoded)));
  const loaded = P.decodeDesignPresets(encoded)[0];
  const recovered = Q.questionnaireReducer(Q.INITIAL_STATE, {
    type: 'restoreDesignPreset', state: P.normalisePresetState(loaded.state),
  });
  assert.deepEqual(Q.buildRunRequest(recovered), Q.buildRunRequest(state));
  assert.equal(recovered.step, 'options');
  assert.equal(recovered.galaxyProfile.config.art_matrix.kickoff.complexity, 4);
});

test('saving has explicit write semantics, does not mutate active state or source profile', () => {
  const before = filled();
  const original = JSON.stringify(before);
  const stored = P.saveDesignPreset([], P.makeDesignPreset('Lattice', before, 1));
  assert.equal(JSON.stringify(before), original);
  assert.equal(stored.length, 1);
  stored[0].state.instruments.risk = 0.1;
  assert.equal(before.instruments.risk, 0.8);
  assert.equal(P.decodeDesignPresets(null).length, 0);
});

test('saving same name updates existing entry without duplicate variants', () => {
  const first = P.makeDesignPreset('Quest', filled(), 100);
  const next = P.makeDesignPreset(' quest ', Q.INITIAL_STATE, 200);
  const stored = P.saveDesignPreset([first], next);
  assert.equal(stored.length, 1);
  assert.equal(stored[0].name, 'quest');
  assert.equal(stored[0].updatedAt, 200);
  assert.equal(stored[0].state.quest.enabled, false);
  assert.equal(P.deleteDesignPreset(stored, 'QUEST').length, 0);
});

test('malformed stored payloads fail closed without silent reset or overwrite', () => {
  const good = P.encodeDesignPresets([P.makeDesignPreset('Saved', filled(), 3)]);
  const bad = [
    '{', 'null', '[]', JSON.stringify({ schema: 'old', entries: [] }),
    JSON.stringify({ schema: P.DESIGN_PRESET_SCHEMA, entries: {} }),
    good.replace(P.DESIGN_PRESET_SCHEMA, 'attacker.schema'),
    'x'.repeat(P.MAX_STORE_CHARS + 1),
  ];
  for (const item of bad) {
    assert.throws(() => P.decodeDesignPresets(item), /preset rejected/i);
  }
  const parsed = JSON.parse(good);
  parsed.entries[0].state.instruments.risk = Infinity;
  // JSON.stringify renders Infinity as null: stored null must not bypass typing.
  assert.throws(() => P.decodeDesignPresets(JSON.stringify(parsed)), /preset rejected/i);
  parsed.entries[0].state.instruments.risk = 0.5;
  parsed.entries[0].state.playable.mode = '../../system';
  assert.throws(() => P.decodeDesignPresets(JSON.stringify(parsed)), /preset rejected/i);
});

test('local capacity, invalid labels and forged choices are bounded', () => {
  const sample = P.makeDesignPreset('Valid', Q.INITIAL_STATE, 4);
  for (const name of ['', ' ', 'x'.repeat(65), 'line\nbreak']) {
    assert.throws(() => P.makeDesignPreset(name, Q.INITIAL_STATE, 5), /preset rejected/i);
  }
  const entries = Array.from({ length: P.MAX_SAVED_PRESETS + 1 },
    (_, i) => ({ ...sample, name: 'Preset ' + i }));
  assert.throws(() => P.encodeDesignPresets(entries), /preset rejected/i);
  assert.throws(() => P.saveDesignPreset(entries.slice(0, 24), sample), /preset rejected/i);
  assert.throws(() => P.makeDesignPreset('bad', Q.INITIAL_STATE, Number.NaN), /preset rejected/i);
  const invalidState = (updates) => ({ ...Q.INITIAL_STATE, ...updates });
  for (const invalid of [
    { instruments: { '__proto__': 0.5, risk: 1.5 } },
    { instruments: { risk: '1' } },
    { instruments: { risk: Infinity } },
    { options: { ...Q.INITIAL_STATE.options, target: 'shell' } },
    { quest: { enabled: true, length: 9 } },
    { playable: { enabled: true, mode: 'evil', launch: true } },
    { quest: { enabled: true, length: 3 }, playable: { enabled: true, mode: 'racing', launch: true } },
  ]) {
    assert.throws(() => P.makeDesignPreset('bad', invalidState(invalid), 8), /preset rejected/i);
  }
});

test('the creator advertises explicit local storage rather than cloud project custody', () => {
  const panel = render(h(Panel, { state: Q.INITIAL_STATE, dispatch: () => {} }));
  assert.match(panel, /data-testid="q-design-preset-library"/);
  assert.match(panel, /data-testid="q-design-presets-toggle"/);
  assert.match(text(panel), /Save \/ load game designs/);
  const page = render(h(Flow, {
    state: { ...Q.INITIAL_STATE, step: 'options' },
    dispatch: () => {}, beats: Q.FALLBACK_BEATS, onForge: () => {},
  }));
  assert.match(page, /data-testid="q-design-preset-library"/);
});

test('no account or provider information is serialized into a design preset', () => {
  const state = { ...filled(), accessToken: 'not-an-allowed-field', apiKey: 'not-an-allowed-field' };
  const encoded = P.encodeDesignPresets([P.makeDesignPreset('My game', state, 2)]);
  assert.doesNotMatch(encoded, /accessToken|apiKey|not-an-allowed-field/);
  assert.doesNotMatch(encoded, /"run_payload"|"secret":|"provider_key"/);
});

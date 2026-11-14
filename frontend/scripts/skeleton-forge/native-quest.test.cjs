'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { h, load, render, text } = require('./harness.cjs');
const Q = load('src/skeletonForge/questionnaire.ts');
const Screen = load('src/skeletonForge/components/QuestionnaireFlow.tsx').default;

function reduce(...actions) {
  return actions.reduce(Q.questionnaireReducer, Q.INITIAL_STATE);
}

function show(state) {
  return render(h(Screen, { state, dispatch: () => {}, beats: Q.FALLBACK_BEATS, onForge: () => {} }));
}

test('default questionnaire and request remain byte-compatible with historical runs', () => {
  assert.equal(Q.INITIAL_STATE.quest.enabled, false);
  assert.equal(Q.INITIAL_STATE.quest.length, 3);
  assert.deepEqual(Q.buildRunRequest(Q.INITIAL_STATE), {
    vision: '', era: null, archetype: 'auto', target: 'godot',
    generation: null, answers: {},
  });
});

test('native quest is explicit and survives from design controls to canonical run request', () => {
  let s = reduce(
    { type: 'setVision', vision: 'Original exploration game' },
    { type: 'setQuestEnabled', value: true },
    { type: 'setQuestLength', value: 7 },
  );
  assert.deepEqual({
    enabled: Q.buildRunRequest(s).quest_content,
    length: Q.buildRunRequest(s).quest_length,
  }, { enabled: true, length: 7 });
  assert.equal(s.quest.enabled, true);
  assert.equal(s.quest.length, 7);
  s = Q.questionnaireReducer(s, { type: 'setQuestEnabled', value: false });
  assert.equal(Q.buildRunRequest(s).quest_content, undefined);
  assert.equal(Q.buildRunRequest(s).quest_length, undefined);
});

test('quests do not falsely advertise playable output for JSON blueprints', () => {
  const s = reduce(
    { type: 'setQuestEnabled', value: true },
    { type: 'setQuestLength', value: 8 },
    { type: 'setOption', key: 'target', value: 'json' },
  );
  assert.equal(Q.buildRunRequest(s).target, 'json');
  assert.equal(Q.buildRunRequest(s).quest_content, undefined);
  assert.equal(Q.buildRunRequest(s).quest_length, undefined);
  const html = show({ ...s, step: 'review' });
  assert.match(text(html), /Native room quests are disabled for JSON blueprint output/);
});

test('native quest lengths are bounded and malformed actions preserve valid state', () => {
  const s = reduce({ type: 'setQuestLength', value: 5 });
  for (const value of [-1, 0, 9, 3.5, NaN, Infinity]) {
    assert.equal(Q.questionnaireReducer(s, { type: 'setQuestLength', value }), s);
  }
  assert.equal(Q.questionnaireReducer(s, { type: 'setQuestLength', value: 1 }).quest.length, 1);
  assert.equal(Q.questionnaireReducer(s, { type: 'setQuestLength', value: 8 }).quest.length, 8);
  assert.equal(Q.questionnaireReducer(s, { type: 'reset' }), Q.INITIAL_STATE);
});

test('creator options exposes native quest controls with accessible explicit 1 to 8 choices', () => {
  const html = show({
    ...Q.INITIAL_STATE,
    step: 'options', vision: 'a dungeon adventure',
    quest: { enabled: true, length: 6 },
  });
  assert.match(html, /data-testid="q-native-quest-controls"/);
  assert.match(html, /data-testid="q-native-quest-on"/);
  assert.match(html, /data-testid="q-native-quest-length"/);
  assert.match(text(html), /Quest objective count: 6/);
  for (let i = 1; i <= 8; i += 1) {
    assert.match(html, new RegExp('data-testid="q-native-quest-' + i + '"'));
  }
});

test('forge review distinguishes actual native quest from ordinary authored game plans', () => {
  let s = reduce(
    { type: 'setVision', vision: 'an original action RPG' },
    { type: 'setQuestEnabled', value: true },
    { type: 'setQuestLength', value: 3 },
  );
  assert.match(text(show({ ...s, step: 'review' })), /Native quest 3 room-entry objectives/);
  s = Q.questionnaireReducer(s, { type: 'setQuestEnabled', value: false });
  assert.doesNotMatch(text(show({ ...s, step: 'review' })), /Native quest 3 room-entry objectives/);
});

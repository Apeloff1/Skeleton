'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { load } = require('./harness.cjs');

const Q = load('src/skeletonForge/questionnaire.ts');
const H = load('src/skeletonForge/creatorBridge.ts');

function make(...actions) {
  return actions.reduce(Q.questionnaireReducer, Q.INITIAL_STATE);
}

test('explicit Forge → Galaxy → Forge handoff retains authored axes, beats and native quest', () => {
  const initial = make(
    { type: 'setVision', vision: 'An original multiplayer racing adventure' },
    { type: 'setBrief', facet: 'genre', value: 'racing' },
    { type: 'setBeat', beat: 'pace', value: 'frantic' },
    { type: 'setAxis', axis: 'tempo', value: 0.72 },
    { type: 'setAxis', axis: 'risk', value: 0.43 },
    { type: 'setQuestEnabled', value: true },
    { type: 'setQuestLength', value: 5 },
  );
  const toGalaxy = H.handoffFromForge(initial, 1700000000000);
  assert.equal(toGalaxy.target, 'galaxy');
  assert.equal(toGalaxy.quest.length, 5);
  const toForge = H.handoffFromGalaxy({
    title: 'New orbital race',
    vision: 'An orbital-racing game with original room challenges',
    genreId: 'fps',
  }, toGalaxy, 1700000000001);
  const restored = H.forgeStateFromHandoff(toForge, 1700000000002);
  assert.ok(restored);
  assert.deepEqual(restored.instruments, { risk: 0.43, tempo: 0.72 });
  assert.deepEqual(restored.beats, { pace: 'frantic' });
  assert.deepEqual(restored.quest, { enabled: true, length: 5 });
  assert.equal(restored.brief.genre, 'fps');
  assert.equal(restored.galaxyGenre, 'fps');
  const request = Q.buildRunRequest(restored);
  assert.equal(request.quest_content, true);
  assert.equal(request.quest_length, 5);
  assert.deepEqual(request.operator_axes, { risk: 0.43, tempo: 0.72 });
  assert.match(request.vision, /orbital-racing/);
  assert.match(request.vision, /Specialized genre:/);
});

test('Galaxy direct navigation populates only compatible Forge vocabulary', () => {
  const draft = H.handoffFromGalaxy({
    title: 'Harbor colony',
    vision: '',
    genreId: 'colony_sim',
  }, null, 1700000000000);
  assert.equal(draft.vision, 'Harbor colony');
  assert.equal(draft.brief.genre, 'simulation');
  const state = H.forgeStateFromHandoff(draft, 1700000000001);
  assert.equal(Q.buildRunRequest(state).answers.genre, 'simulation');
  assert.equal(Q.buildRunRequest(state).quest_content, undefined);
  assert.deepEqual(state.instruments, {});
});

test('authoring handoff supports numeric-leading historical genres without changing choices', () => {
  const original = make({ type: 'setBrief', facet: 'genre', value: '4x' });
  const output = H.handoffFromForge(original, 1700000000000);
  assert.equal(output.brief.genre, '4x');
  assert.equal(H.handoffFromGalaxy({ title: '', vision: '', genreId: null }, output, 1700000000001).brief.genre, '4x');
});

test('a requested JSON export keeps quest config as a draft but never enables native quest output', () => {
  const s = make(
    { type: 'setVision', vision: 'A low-fi text adventure' },
    { type: 'setQuestEnabled', value: true },
    { type: 'setQuestLength', value: 8 },
    { type: 'setOption', key: 'target', value: 'json' },
  );
  const d = H.handoffFromForge(s, 1700000000000);
  const restored = H.forgeStateFromHandoff(
    H.handoffFromGalaxy({ title: '', vision: '', genreId: null }, d, 1700000000001),
    1700000000002,
  );
  assert.equal(restored.options.target, 'json');
  assert.deepEqual(restored.quest, { enabled: true, length: 8 });
  assert.equal(Q.buildRunRequest(restored).quest_content, undefined);
});

test('single-use bridge validation rejects stale, forged and off-direction messages', () => {
  const original = H.handoffFromForge(Q.INITIAL_STATE, 1700000000000);
  assert.equal(H.parseCreatorBridge(original, 'forge', 1700000000001), null);
  assert.equal(H.parseCreatorBridge(original, 'galaxy', 1700000000000 + H.CREATOR_BRIDGE_TTL_MS + 1), null);
  assert.equal(H.parseCreatorBridge(original, 'galaxy', 1699999969999), null);
  assert.equal(H.parseCreatorBridge({ ...original, schema: 'unknown.v1' }, 'galaxy', 1700000000001), null);
  assert.equal(H.parseCreatorBridge({ ...original, createdMs: '1700000000000' }, 'galaxy', 1700000000001), null);
});

test('untrusted duplicate/unsafe choice and axis keys cannot poison restored request', () => {
  const raw = JSON.parse(JSON.stringify(H.handoffFromForge(Q.INITIAL_STATE, 1700000000000)));
  raw.brief = { __proto__: 'pollute', genre: 'colony-sim', constructor: 'unsafe' };
  raw.instruments = { __proto__: { polluted: true }, risk: 0.7, tempo: '0.3', bad: 0.4, agency: 2 };
  raw.quest = { enabled: true, length: Infinity };
  const safe = H.parseCreatorBridge(raw, 'galaxy', 1700000000001);
  assert.equal(safe.brief.genre, 'colony-sim');
  assert.equal(Object.hasOwn(safe.brief, '__proto__'), false);
  assert.deepEqual(safe.instruments, { risk: 0.7 });
  assert.deepEqual(safe.quest, { enabled: true, length: 3 });
});

test('Galaxy and Forge routes only hand off after explicit user action', () => {
  const root = path.resolve(__dirname, '../..');
  const forgeRoute = fs.readFileSync(path.join(root, 'app/skeleton-forge.tsx'), 'utf8');
  const galaxyRoute = fs.readFileSync(path.join(root, 'app/galaxy.tsx'), 'utf8');
  const galaxyModal = fs.readFileSync(path.join(root, 'src/features/GalaxyStudioFactory/GalaxyStudioFactoryModal.tsx'), 'utf8');
  assert.match(forgeRoute, /storeCreatorBridge\(handoffFromForge\(draft\)\)/);
  assert.match(forgeRoute, /onOpenGalaxyStudio=\{openGalaxy\}/);
  assert.match(galaxyRoute, /storeCreatorBridge\(handoffFromGalaxy\(selection, incoming\)\)/);
  assert.match(galaxyModal, /testID="galaxy-continue-in-gameforge"/);
  assert.match(galaxyModal, /onPress=\{\(\) => onSendToForge\(\{/);
  assert.doesNotMatch(forgeRoute, /onOpenGalaxyStudio=\{\(\) => router\.push/);
});

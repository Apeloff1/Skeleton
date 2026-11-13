'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { load } = require('./harness.cjs');

const Q = load('src/skeletonForge/questionnaire.ts');
const H = load('src/skeletonForge/creatorBridge.ts');
const Galaxy = load('src/skeletonForge/galaxyGenres.ts');
const { GALAXY_OFFLINE_CHOICES } = load('src/features/GalaxyStudioFactory/genreRegistry.ts');
const { GENRE_CHOICES } = load('src/skeletonForge/genreCatalog.ts');

function make(...actions) {
  return actions.reduce(Q.questionnaireReducer, Q.INITIAL_STATE);
}

test('all distinct historical Galaxy fallback genres map into 158-choice GameForge', () => {
  const tokens = new Set(GENRE_CHOICES);
  const ids = GALAXY_OFFLINE_CHOICES.map(x => x.id);
  assert.equal(ids.length, 69);
  assert.equal(new Set(ids).size, 69);
  assert.equal(Galaxy.GALAXY_CHOICES.length, 69);
  assert.deepEqual(new Set(Object.keys(Galaxy.GALAXY_TO_FORGE_BRIEF)), new Set(ids));
  for (const id of ids) {
    const mapped = Galaxy.mappedBriefGenre(id);
    assert.ok(mapped && tokens.has(mapped), 'No supported brief vote for historical genre ' + id);
    const state = make({ type: 'setGalaxyGenre', genre: id });
    assert.equal(Q.buildRunRequest(state).answers.genre, mapped, id);
    const forward = H.handoffFromGalaxy({ title: 'Example', vision: '', genreId: id }, null, 1700000000000);
    assert.equal(forward.galaxyGenre, id);
    assert.equal(forward.brief.genre, mapped);
  }
  assert.equal(Galaxy.mappedBriefGenre('beat_em_up'), 'beat-em-up');
  assert.equal(Galaxy.mappedBriefGenre('shoot_em_up'), 'shoot-em-up');
});

test('backend-fetched Galaxy-only genres map into the expanded 158-choice brief without false specialty', () => {
  const draft = H.handoffFromGalaxy({
    title: 'A needle-jump platformer',
    vision: 'Precision movement through shrinking rooms',
    genreId: 'precision_platformer',
  }, null, 1700000000000);
  assert.equal(draft.brief.genre, 'precision-platformer');
  assert.equal(draft.galaxyGenre, null);
  const state = H.forgeStateFromHandoff(draft, 1700000000001);
  assert.equal(Q.buildRunRequest(state).answers.genre, 'precision-platformer');
  assert.doesNotMatch(Q.buildRunRequest(state).vision, /Specialized genre:/);
  assert.throws(() => H.handoffFromGalaxy({
    title: 'An unknown genre', vision: '', genreId: 'unknown_private_genre',
  }, null, 1700000000000), /no compatible GameForge mapping/);
});

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

test('full questionnaire progress survives passive close and explicit return without skipping blocked steps', () => {
  const filled = make(
    { type: 'setVision', vision: 'An original narrative strategy game' },
    { type: 'setBrief', facet: 'genre', value: 'strategy' },
    { type: 'setBeat', beat: 'pace', value: 'unhurried' },
    { type: 'goto', step: 'review' },
  );
  assert.equal(filled.step, 'review');
  const toGalaxy = H.handoffFromForge(filled, 1700000000000);
  assert.equal(toGalaxy.step, 'review');
  const toForge = H.handoffFromGalaxy(
    { title: '', vision: '', genreId: null }, toGalaxy, 1700000000001,
  );
  assert.equal(toForge.step, 'review');
  const returned = H.forgeStateFromHandoff(toForge, 1700000000002);
  assert.equal(returned.step, 'review');
  assert.equal(returned.brief.genre, 'strategy');
  assert.equal(returned.beats.pace, 'unhurried');

  const forged = { ...toForge, step: 'review', vision: '', brief: {}, beats: {} };
  const fenced = H.forgeStateFromHandoff(forged, 1700000000002);
  assert.equal(fenced.step, 'vision');
  assert.equal(H.parseCreatorBridge({ ...toForge, step: 'not-a-step' }, 'forge', 1700000000002).step, 'brief');
});

test('Galaxy navigation retains opted-in playable sidecar scenes and original quest controls', () => {
  const original = make(
    { type: 'setVision', vision: 'An orbital dungeon crawler' },
    { type: 'setPlayableEnabled', value: true },
    { type: 'setQuestEnabled', value: true },
    { type: 'setQuestLength', value: 4 },
  );
  const accepted = H.handoffFromForge(original, 1700000000000);
  assert.equal(accepted.playable.enabled, true);
  const outbound = H.handoffFromGalaxy(
    { title: 'A new title', vision: '', genreId: null }, accepted,
    1700000000000 + 24 * 60 * 60 * 1000,
  );
  const restored = H.forgeStateFromHandoff(outbound, outbound.createdMs + 1);
  assert.equal(restored.playable.enabled, true);
  assert.equal(restored.quest.length, 4);
  assert.equal(Q.buildRunRequest(restored).playable_content, true);
  assert.equal(Q.buildRunRequest(restored).quest_content, true);
});

test('headless Godot qualification selection survives long Galaxy editing without changing defaults', () => {
  const original = make(
    { type: 'setVision', vision: 'A full offline boardgame world' },
    { type: 'setPlayableEnabled', value: true },
    { type: 'setPlaytestMode', value: 'require' },
  );
  const accepted = H.handoffFromForge(original, 1700000000000);
  const changed = H.handoffFromGalaxy(
    { title: '', vision: '', genreId: null },
    accepted, 1700000000000 + 5 * 3600 * 1000,
  );
  const restored = H.forgeStateFromHandoff(changed, changed.createdMs + 1);
  assert.equal(restored.playtest, 'require');
  assert.equal(Q.buildRunRequest(restored).playtest, 'require');
  const unexpected = H.parseCreatorBridge({
    ...changed, playtest: 'execute-something-else',
  }, 'forge', changed.createdMs + 1);
  assert.equal(unexpected.playtest, 'off');
  assert.equal(H.handoffFromGalaxy({
    title: '', vision: 'New', genreId: null,
  }, null, 1700000000000).playtest, 'off');
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
  assert.equal(Object.hasOwn(safe.brief, 'constructor'), false);
  assert.deepEqual(safe.instruments, { risk: 0.7 });
  assert.deepEqual(safe.quest, { enabled: true, length: 3 });
});

test('editing in Galaxy for hours does not discard a previously accepted Forge draft', () => {
  const createdMs = 1700000000000;
  const initial = make(
    { type: 'setVision', vision: 'A cooperative dungeon builder' },
    { type: 'setBeat', beat: 'space', value: 'dungeon' },
    { type: 'setAxis', axis: 'tempo', value: 0.71 },
    { type: 'setQuestEnabled', value: true },
    { type: 'setQuestLength', value: 8 },
  );
  const accepted = H.handoffFromForge(initial, createdMs);
  assert.equal(H.parseCreatorBridge(accepted, 'galaxy', createdMs + H.CREATOR_BRIDGE_TTL_MS + 1), null);
  const outbound = H.handoffFromGalaxy({ title: '', vision: '', genreId: null }, accepted, createdMs + 4 * 3600 * 1000);
  const restored = H.forgeStateFromHandoff(outbound, createdMs + 4 * 3600 * 1000 + 1);
  assert.equal(restored.vision, 'A cooperative dungeon builder');
  assert.equal(restored.beats.space, 'dungeon');
  assert.equal(restored.instruments.tempo, 0.71);
  assert.equal(restored.quest.length, 8);
  assert.equal(Q.buildRunRequest(restored).quest_content, true);
});

test('Galaxy and Forge routes only hand off after explicit user action', () => {
  const root = path.resolve(__dirname, '../..');
  const forgeRoute = fs.readFileSync(path.join(root, 'app/skeleton-forge.tsx'), 'utf8');
  const galaxyRoute = fs.readFileSync(path.join(root, 'app/galaxy.tsx'), 'utf8');
  const galaxyModal = fs.readFileSync(path.join(root, 'src/features/GalaxyStudioFactory/GalaxyStudioFactoryModal.tsx'), 'utf8');
  assert.match(forgeRoute, /storeCreatorBridge\(handoffFromForge\(draft, Date\.now\(\), incoming\)\)/);
  assert.match(forgeRoute, /onOpenGalaxyStudio=\{openGalaxy\}/);
  assert.match(galaxyRoute, /storeCreatorBridge\(handoffFromGalaxy\(selection, incoming\)\)/);
  assert.match(galaxyModal, /testID="galaxy-send-full-design-to-gameforge"/);
  assert.match(galaxyModal, /onPress=\{sendToGameForge\}/);
  assert.match(galaxyModal, /await saveGalaxyDraft\(snapshot\)/);
  assert.match(galaxyModal, /GALAXY_DRAFT_SCHEMA/);
  assert.match(galaxyRoute, /await storeCreatorBridge\(handoffFromGalaxy\(selection, incoming\)\)/);
  // Direct close should restore the original Forge draft as a fresh
  // one-time message; only explicit Continue applies Galaxy edits.
  assert.match(galaxyRoute, /if \(incoming\) \{/);
  assert.match(galaxyRoute, /const previous = handoffFromGalaxy\(/);
  assert.match(galaxyRoute, /await storeCreatorBridge\(previous\)/);
  assert.match(galaxyRoute, /router\.replace\(\{/);

  assert.match(galaxyModal, /await onSendToForge\(\{/);
  assert.match(galaxyModal, /handoffLock\.current = true/);
  assert.doesNotMatch(forgeRoute, /onOpenGalaxyStudio=\{\(\) => router\.push/);
});

test('Studio → Forge → Studio preserves full authored questionnaire and origin revision', () => {
  const initial = make(
    { type: 'setVision', vision: 'A handcrafted local fantasy world' },
    { type: 'setBrief', facet: 'genre', value: 'rpg' },
    { type: 'setAxis', axis: 'risk', value: 0.66 },
    { type: 'setQuestEnabled', value: true },
    { type: 'setPlayableEnabled', value: true },
    { type: 'setSourceExportEnabled', value: true },
    { type: 'setPlaytestMode', value: 'require' },
    { type: 'goto', step: 'review' },
  );
  const edited = Q.questionnaireReducer(initial,
    { type: 'setAxis', axis: 'tempo', value: 0.28 });
  const source = H.handoffFromStudio(initial, 'p_abc_0', '2026-11-13T13:00:00.000Z', 1700000000000);
  assert.equal(source.target, 'forge');
  assert.equal(source.studioProjectId, 'p_abc_0');
  assert.equal(source.studioProjectUpdatedAt, '2026-11-13T13:00:00.000Z');
  const outgoing = H.handoffToStudio(edited, source, 1700000000000 + 60 * 60 * 1000);
  assert.equal(outgoing.target, 'studio');
  assert.equal(outgoing.studioProjectId, 'p_abc_0');
  const restored = H.studioStateFromHandoff(outgoing, outgoing.createdMs + 1);
  assert.equal(restored.step, 'review');
  assert.equal(restored.vision, initial.vision);
  assert.deepEqual(restored.instruments, { risk: 0.66, tempo: 0.28 });
  assert.equal(restored.quest.enabled, true);
  assert.equal(restored.playable.enabled, true);
  assert.equal(restored.sourceExport.enabled, true);
  assert.equal(restored.playtest, 'require');
  assert.equal(Q.buildRunRequest(restored).include_files, true);
  assert.equal(Q.buildRunRequest(restored).quest_content, true);
});

test('Studio origin survives a Galaxy detour and cannot be forged from unrelated work', () => {
  const state = make({ type: 'setVision', vision: 'A hand-crafted original quest' });
  const studio = H.handoffFromStudio(state, 'p_origin', '2026-11-13T13:00:00.000Z', 1700000000000);
  const galaxy = H.handoffFromForge(state, 1700000001000, studio);
  assert.equal(galaxy.studioProjectId, 'p_origin');
  const returnedForge = H.handoffFromGalaxy(
    { title: '', vision: '', genreId: null }, galaxy, 1700000002000);
  assert.equal(returnedForge.studioProjectId, 'p_origin');
  assert.equal(H.handoffToStudio(state, returnedForge, 1700000003000).target, 'studio');
  assert.throws(() => H.handoffToStudio(
    state, H.handoffFromGalaxy({ title: '', vision: '', genreId: null }, null, 1700000000000),
    1700000000001,
  ), /was not opened from a Studio project/);
  assert.throws(() => H.handoffFromStudio(
    state, '../escape', '2026-11-13T13:00:00.000Z', 1700000000000,
  ), /Unrecognized source Studio/);
  const tampered = { ...studio, studioProjectId: '../hijack' };
  assert.equal(H.parseCreatorBridge(tampered, 'forge', 1700000000001).studioProjectId, null);
  assert.equal(H.studioStateFromHandoff({ ...studio, target: 'studio' }, 1700000000001) !== null, true);
  assert.equal(H.studioStateFromHandoff({
    ...studio, target: 'studio', studioProjectUpdatedAt: 'not-an-ISO-date',
  }, 1700000000001), null);
});

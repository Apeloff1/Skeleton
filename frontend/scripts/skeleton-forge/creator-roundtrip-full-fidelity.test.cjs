'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const Module = require('node:module');
const { load } = require('./harness.cjs');

const kv = new Map();
const auth = { token: 'alice-offline-bearer', epoch: 1 };
const storage = {
  getItem: async key => kv.get(key) ?? null,
  setItem: async (key, value) => { kv.set(key, value); },
  removeItem: async key => { kv.delete(key); },
};
const original = Module._load;
Module._load = function(request, parent, isMain) {
  if (request === '@react-native-async-storage/async-storage') {
    return { __esModule: true, default: storage };
  }
  if (request === 'expo-crypto') {
    return {
      CryptoDigestAlgorithm: { SHA256: 'SHA-256' },
      digestStringAsync: async (_, value) => crypto.createHash('sha256').update(value).digest('hex'),
    };
  }
  if (request === '../auth/gameforgeAuth') return {
    getAuthEpoch: () => auth.epoch,
    getAuthToken: () => auth.token,
    initializeStoredToken: async () => {},
  };
  return original.call(this, request, parent, isMain);
};
let bridgeStorage, galaxyStorage, Draft;
try {
  bridgeStorage = load('src/skeletonForge/creatorBridgeStorage.ts');
  galaxyStorage = load('src/features/GalaxyStudioFactory/draftCustody.ts');
  Draft = load('src/features/GalaxyStudioFactory/galaxyDraftCodec.ts');
} finally {
  Module._load = original;
}
const Q = load('src/skeletonForge/questionnaire.ts');
const H = load('src/skeletonForge/creatorBridge.ts');
const G = load('src/skeletonForge/galaxyHandoff.ts');

function fullProfile() {
  const x = {
    title: 'Future Harbor', genre: 'beat_em_up',
    game_vision: 'Handcrafted cooperative action brawler',
    narrative_phases: { prologue: { count: 4 } },
    style_params: { graphics_style: 'pixel_art' },
    extra_params: { authored_slider_1: 99 },
  };
  for (const family of G.MATRIX_FIELDS) x[family] = { prologue: { count: 3 } };
  return G.normaliseGalaxyProfile(x);
}
function setup() {
  return {
    ...Q.INITIAL_STATE, step: 'review',
    vision: 'An original handcrafted world',
    brief: { genre: 'rpg' },
    beats: { pace: 'unhurried', space: 'dungeon' },
    instruments: { tempo: 0.71, risk: 0.22 },
    playable: { enabled: true, mode: 'stealth', launch: true },
    quest: { enabled: false, length: 6 },
    playtest: 'require',
    sourceExport: { enabled: true },
    galaxyProfile: fullProfile(),
  };
}

test('all 8 native sidecar modes and full 14-matrix source survive Forge > Galaxy > Forge', () => {
  for (const { id } of Q.PLAYABLE_SLICES) {
    const source = { ...setup(), playable: { enabled: true, mode: id, launch: true } };
    const first = H.handoffFromForge(source, 1700000000000);
    const outbound = H.handoffFromGalaxy({
      title: 'Future Harbor', vision: '', genreId: 'beat_em_up',
    }, first, 1700000000001);
    const restored = H.forgeStateFromHandoff(outbound, 1700000000002);
    const request = Q.buildRunRequest(restored);
    assert.equal(restored.playable.mode, id);
    assert.equal(restored.playable.launch, true);
    assert.equal(restored.step, 'review');
    assert.deepEqual(restored.instruments, { tempo: 0.71, risk: 0.22 });
    assert.deepEqual(restored.beats, { pace: 'unhurried', space: 'dungeon' });
    assert.equal(request.playable_archetype, id);
    assert.equal(request.playtest, 'require');
    assert.equal(request.include_files, true);
    assert.equal(request.galaxy_profile.config.extra_params.authored_slider_1, 99);
    assert.equal(G.MATRIX_FIELDS.filter(k => request.galaxy_profile.config[k]).length, 14);
  }
});

test('bridge rejects forged full Galaxy source rather than silently degrading content', () => {
  const x = H.handoffFromForge(setup(), 1700000000000);
  const forged = {
    ...x,
    galaxyProfile: {
      ...x.galaxyProfile,
      config: { ...x.galaxyProfile.config, mechanics_matrix: null },
    },
  };
  assert.equal(H.parseCreatorBridge(forged, 'galaxy', 1700000000000), null);
  assert.equal(H.parseCreatorBridge({ ...x, galaxyProfile: { schema: 'evil.v1', config: {} } },
    'galaxy', 1700000000000), null);
});

test('one-time Galaxy/Forge handoff remains owner scoped and single consumption', async () => {
  const first = H.handoffFromForge(setup());
  await bridgeStorage.storeCreatorBridge(first);
  assert.equal((await bridgeStorage.consumeCreatorBridge('forge')), null,
    'wrong-direction reader cannot discard valid handoff');
  const [a, b] = await Promise.all([
    bridgeStorage.consumeCreatorBridge('galaxy'),
    bridgeStorage.consumeCreatorBridge('galaxy'),
  ]);
  assert.equal([a, b].filter(Boolean).length, 1);
  assert.equal(a?.playable.mode ?? b?.playable.mode, 'stealth');
  assert.equal((a ?? b).galaxyProfile.config.extra_params.authored_slider_1, 99);
  assert.equal(await bridgeStorage.consumeCreatorBridge('galaxy'), null);
  assert.ok([...kv.keys()].every(key => !key.includes(auth.token)));
});

test('auth rotation prevents cross-account retrieval of private editor drafts', async () => {
  const saved = {
    schema: Draft.GALAXY_DRAFT_SCHEMA, savedMs: Date.now(),
    title: 'Alice only', gameVision: 'Original', genreId: 'puzzle',
    matrices: { mechanics: { prologue: { complexity: 900 } } },
    narrative: { prologue: { count: 1 } }, extraParams: { complexity: 55 },
  };
  await galaxyStorage.saveGalaxyDraft(saved);
  auth.token = 'bob-offline-bearer'; auth.epoch++;
  assert.equal(await galaxyStorage.loadGalaxyDraft(), null);
  await bridgeStorage.storeCreatorBridge(H.handoffFromForge(setup()));
  auth.token = 'alice-offline-bearer'; auth.epoch++;
  const restored = await galaxyStorage.loadGalaxyDraft();
  assert.equal(restored.title, 'Alice only');
  assert.equal(restored.matrices.mechanics.prologue.complexity, 900);
  assert.equal(await bridgeStorage.consumeCreatorBridge('galaxy'), null);
  auth.token = 'bob-offline-bearer'; auth.epoch++;
  assert.ok(await bridgeStorage.consumeCreatorBridge('galaxy'));
});

test('expired handoffs and changed account during storage are fail-closed', async () => {
  const first = H.handoffFromForge(setup(), 1700000000000);
  assert.equal(H.parseCreatorBridge(first, 'galaxy', 1700000000000 + H.CREATOR_BRIDGE_TTL_MS + 1), null);
  const prev = storage.setItem;
  storage.setItem = async (key, value) => {
    await prev(key, value);
    auth.token = 'new-account'; auth.epoch++;
  };
  await assert.rejects(bridgeStorage.storeCreatorBridge(H.handoffFromForge(setup())), /Account changed/);
  assert.equal(await bridgeStorage.consumeCreatorBridge('galaxy'), null);
  storage.setItem = prev;
});

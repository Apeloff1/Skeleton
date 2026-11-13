'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const Module = require('node:module');
const { createHash } = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const { load } = require('./harness.cjs');

const savedLoad = Module._load;
const kv = new Map();
let bearer = 'alice-offline-bearer';
let epoch = 1;
let rotateOnWrite = false;
const mockAuth = {
  initializeStoredToken: async () => {},
  getAuthToken: () => bearer,
  getAuthEpoch: () => epoch,
};
const mockCrypto = {
  CryptoDigestAlgorithm: { SHA256: 'sha256' },
  digestStringAsync: async (algorithm, value) => {
    assert.equal(algorithm, 'sha256');
    return createHash('sha256').update(value).digest('hex');
  },
};
const mockStorage = {
  getItem: async (key) => kv.get(key) ?? null,
  setItem: async (key, value) => {
    kv.set(key, value);
    if (rotateOnWrite) {
      rotateOnWrite = false;
      bearer = 'bob-offline-bearer';
      epoch += 1;
    }
  },
  removeItem: async (key) => { kv.delete(key); },
};
let scope, bridgeStorage, galaxyStorage, studioStorage;
try {
  Module._load = function isolatedAuthAndStorage(request, parent, isMain) {
    if (request === 'expo-crypto') return mockCrypto;
    if (request === '../auth/gameforgeAuth') return mockAuth;
    if (request === '@react-native-async-storage/async-storage') return {
      __esModule: true, default: mockStorage,
    };
    return savedLoad.apply(this, [request, parent, isMain]);
  };
  scope = load('src/skeletonForge/creatorStorageScope.ts');
  bridgeStorage = load('src/skeletonForge/creatorBridgeStorage.ts');
  galaxyStorage = load('src/features/GalaxyStudioFactory/draftCustody.ts');
  studioStorage = load('src/skeletonForge/foundation/storageDevice.ts');
} finally {
  Module._load = savedLoad;
}
const H = load('src/skeletonForge/creatorBridge.ts');
const Q = load('src/skeletonForge/questionnaire.ts');

test.beforeEach(() => {
  kv.clear();
  bearer = 'alice-offline-bearer';
  epoch = 1;
  rotateOnWrite = false;
});

test('SHA-256 scoped local keys cannot expose raw bearer values', async () => {
  const alice = await scope.creatorStorageScope('@skeleton_galaxy_editor_draft_v1');
  assert.ok(alice.stillCurrent());
  assert.match(alice.key, /:([0-9a-f]{64})$/);
  assert.doesNotMatch(alice.key, /alice-offline-bearer/);
  bearer = 'bob-offline-bearer';
  epoch += 1;
  const bob = await scope.creatorStorageScope('@skeleton_galaxy_editor_draft_v1');
  assert.notEqual(alice.key, bob.key);
  assert.equal(alice.stillCurrent(), false);
  await assert.rejects(scope.creatorStorageScope('@other_namespace'), /Unrecognized/);
  bearer = '';
  epoch += 1;
  assert.match((await scope.creatorStorageScope('@skeleton_creator_bridge_v1')).key, /:anonymous$/);
});

test('one account cannot consume another local creator handoff', async () => {
  const draft = H.handoffFromForge(Q.INITIAL_STATE);
  await bridgeStorage.storeCreatorBridge(draft);
  assert.equal(kv.size, 1);
  bearer = 'bob-offline-bearer';
  epoch += 1;
  assert.equal(await bridgeStorage.consumeCreatorBridge('galaxy'), null);
  assert.equal(kv.size, 1);
  bearer = 'alice-offline-bearer';
  epoch += 1;
  const restored = await bridgeStorage.consumeCreatorBridge('galaxy');
  assert.equal(restored.schema, H.CREATOR_BRIDGE_SCHEMA);
  assert.equal(kv.size, 0);
});

test('parallel readers in one runtime cannot double-consume a single verified handoff', async () => {
  await bridgeStorage.storeCreatorBridge(H.handoffFromForge(Q.INITIAL_STATE));
  const claims = await Promise.all(
    Array.from({ length: 12 }, () => bridgeStorage.consumeCreatorBridge('galaxy')),
  );
  assert.equal(claims.filter(Boolean).length, 1);
  assert.equal(kv.size, 0);
});

test('wrong-direction read preserves the one-time message for its intended receiver', async () => {
  await bridgeStorage.storeCreatorBridge(H.handoffFromForge(Q.INITIAL_STATE));
  assert.equal(await bridgeStorage.consumeCreatorBridge('forge'), null);
  assert.equal(kv.size, 1);
  const correct = await bridgeStorage.consumeCreatorBridge('galaxy');
  assert.equal(correct?.target, 'galaxy');
  assert.equal(kv.size, 0);
});

test('Galaxy advanced draft is isolated by bearer without a network check', async () => {
  await galaxyStorage.saveGalaxyDraft({
    schema: galaxyStorage.GALAXY_DRAFT_SCHEMA, savedMs: Date.now(),
    title: 'Alice private design', gameVision: 'A distinct offline world',
    matrices: { mechanics: { phase_1: { intensity: 555 } } },
    extraParams: { palette: 38 },
  });
  assert.equal(kv.size, 1);
  bearer = 'bob-offline-bearer';
  epoch += 1;
  assert.equal(await galaxyStorage.loadGalaxyDraft(), null);
  bearer = 'alice-offline-bearer';
  epoch += 1;
  const restored = await galaxyStorage.loadGalaxyDraft();
  assert.equal(restored.title, 'Alice private design');
  assert.equal(restored.matrices.mechanics.phase_1.intensity, 555);
});

test('auth rotation while AsyncStorage is writing fails closed and purges the partial publication', async () => {
  rotateOnWrite = true;
  await assert.rejects(
    bridgeStorage.storeCreatorBridge(H.handoffFromForge(Q.INITIAL_STATE)),
    /Account changed/,
  );
  assert.equal(kv.size, 0);
  bearer = 'alice-offline-bearer';
  epoch += 1;
  rotateOnWrite = true;
  await assert.rejects(
    galaxyStorage.saveGalaxyDraft({
      schema: galaxyStorage.GALAXY_DRAFT_SCHEMA,
      savedMs: Date.now(), title: 'Cannot leak',
    }),
    /Account changed/,
  );
  assert.equal(kv.size, 0);
});

test('both routes unmount old editor state as soon as authentication epoch changes', () => {
  const root = path.resolve(__dirname, '../..');
  for (const rel of ['app/galaxy.tsx', 'app/skeleton-forge.tsx']) {
    const source = fs.readFileSync(path.join(root, rel), 'utf8');
    assert.match(source, /subscribeAuthChanges\(\(\) => setAuthEpoch\(getAuthEpoch\(\)\)\)/);
    assert.match(source, /loadedAuthEpoch === authEpoch/);
    assert.match(source, /consumeCreatorBridge\(/);
    assert.match(source, /loadGalaxyDraft\(/);
  }
});

test('first-install Studio project keys are isolated across accounts without storing bearer tokens', async () => {
  const alice = studioStorage.asyncStorageKv();
  await alice.setItem('skeleton.studio.projects.v1', '[{"title":"Alice original design"}]');
  assert.equal(await alice.getItem('skeleton.studio.projects.v1'), '[{"title":"Alice original design"}]');
  assert.ok([...kv.keys()].every(key => !key.includes('alice-offline-bearer')));
  assert.equal(kv.size, 1);
  bearer = 'bob-offline-bearer';
  epoch++;
  const bob = studioStorage.asyncStorageKv();
  assert.equal(await bob.getItem('skeleton.studio.projects.v1'), null);
  await bob.setItem('skeleton.studio.projects.v1', '[{"title":"Bob original design"}]');
  assert.equal(kv.size, 2);
  bearer = 'alice-offline-bearer';
  epoch++;
  assert.equal(await alice.getItem('skeleton.studio.projects.v1'), '[{"title":"Alice original design"}]');
  await assert.rejects(alice.getItem('unrecognized-project-file'), /Unexpected/);
  await assert.rejects(alice.setItem('unrecognized-project-file', 'private'), /Unexpected/);
});

test('legacy unscoped projects are only read by an explicit migration adapter', async () => {
  assert.equal(await studioStorage.hasLegacyStudioProjects(), false);
  kv.set('skeleton.studio.projects.v1', '[{"title":"Unknown legacy project"}]');
  assert.equal(await studioStorage.hasLegacyStudioProjects(), true);
  assert.equal(await studioStorage.asyncStorageKv().getItem('skeleton.studio.projects.v1'), null);
  const old = studioStorage.legacyReadOnlyKv();
  assert.equal(await old.getItem('skeleton.studio.projects.v1'), '[{"title":"Unknown legacy project"}]');
  await assert.rejects(old.setItem('skeleton.studio.projects.v1', 'overwrite'), /read-only/);
  assert.equal(kv.get('skeleton.studio.projects.v1'), '[{"title":"Unknown legacy project"}]');
});

test('account rotation while writing Studio projects rejects publication to the incoming account', async () => {
  const store = studioStorage.asyncStorageKv();
  rotateOnWrite = true;
  await assert.rejects(
    store.setItem('skeleton.studio.projects.v1', '[{"title":"Alice only"}]'),
    /Account changed during Studio project write/,
  );
  assert.equal(bearer, 'bob-offline-bearer');
  assert.equal(await store.getItem('skeleton.studio.projects.v1'), null);
  bearer = 'alice-offline-bearer';
  epoch++;
  assert.match(await store.getItem('skeleton.studio.projects.v1'), /Alice only/);
});

test('first-install Studio unmounts old local projects when the signed-in account changes', () => {
  const src = fs.readFileSync(
    path.resolve(__dirname, '../../src/skeletonForge/components/foundation/FoundationScreen.tsx'),
    'utf8',
  );
  assert.match(src, /setAuthEpoch\(getAuthEpoch\(\)\)/);
  assert.match(src, /key=\{authEpoch\}/);
  assert.match(src, /legacyReadOnlyKv\(\)/);
  assert.match(src, /hasLegacyStudioProjects\(\)/);
});

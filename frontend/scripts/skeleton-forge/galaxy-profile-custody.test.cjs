'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const Module = require('node:module');
const { load } = require('./harness.cjs');

const stored = new Map();
const auth = { token: 'account-A', epoch: 1 };
const nativeStorage = {
  getItem: async key => stored.has(key) ? stored.get(key) : null,
  setItem: async (key, value) => { stored.set(key, value); },
  removeItem: async key => { stored.delete(key); },
};
const original = Module._load;
Module._load = function(request, parent, isMain) {
  if (request === '@react-native-async-storage/async-storage') {
    return { __esModule: true, default: nativeStorage };
  }
  if (request === 'expo-crypto') {
    return {
      CryptoDigestAlgorithm: { SHA256: 'SHA-256' },
      digestStringAsync: async (_, value) =>
        crypto.createHash('sha256').update(value).digest('hex'),
    };
  }
  if (request === '../auth/gameforgeAuth') {
    return {
      getAuthEpoch: () => auth.epoch,
      getAuthToken: () => auth.token,
      initializeStoredToken: async () => {},
    };
  }
  return original.call(this, request, parent, isMain);
};
const custody = load('src/skeletonForge/galaxyProfileCustody.ts');
const galaxy = load('src/skeletonForge/galaxyHandoff.ts');
Module._load = original;

function complete() {
  const game = {
    title: 'The Great Sandglass', genre: 'shoot_em_up',
    extra_params: { quest_variety: 99 },
    style_params: { graphic_style: 'pixel_art' },
    narrative_phases: { prologue: { count: 7 } },
  };
  for (const matrix of galaxy.MATRIX_FIELDS) game[matrix] = { chapter1: { count: 8 } };
  return game;
}

test('explicit local save restores full Galaxy matrices within the same account', async () => {
  await custody.saveGalaxyProfile(complete());
  const saved = await custody.loadGalaxyProfile();
  assert.equal(saved.config.genre, 'shoot_em_up');
  assert.equal(saved.config.extra_params.quest_variety, 99);
  assert.equal(galaxy.MATRIX_FIELDS.filter(f => saved.config[f]).length, 14);
  assert.ok([...stored.keys()][0].startsWith('@skeleton_galaxy_profile_snapshot_v1:'));
  assert.ok(![...stored.keys()][0].includes('account-A'));
});
test('changing account never shows a previous account design', async () => {
  auth.token = 'account-B'; auth.epoch++;
  assert.equal(await custody.loadGalaxyProfile(), null);
  await custody.saveGalaxyProfile({ ...complete(), title: 'B only' });
  assert.equal((await custody.loadGalaxyProfile()).config.title, 'B only');
  auth.token = 'account-A'; auth.epoch++;
  assert.equal((await custody.loadGalaxyProfile()).config.title, 'The Great Sandglass');
});
test('clear is scoped to current account and never resurrects previous draft', async () => {
  await custody.clearSavedGalaxyProfile();
  assert.equal(await custody.loadGalaxyProfile(), null);
  auth.token = 'account-B'; auth.epoch++;
  assert.equal((await custody.loadGalaxyProfile()).config.title, 'B only');
});

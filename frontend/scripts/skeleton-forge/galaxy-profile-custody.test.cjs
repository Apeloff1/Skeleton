'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const Module = require('node:module');
const { load } = require('./harness.cjs');

const stored = new Map();
const auth = { token: 'account-A', epoch: 1 };
let rotateDuringWrite = false;
let rotateDuringRemove = false;
let replacementDuringWrite = null;
let replacementDuringRemove = null;
const nativeStorage = {
  getItem: async key => stored.has(key) ? stored.get(key) : null,
  setItem: async (key, value) => {
    stored.set(key, value);
    if (rotateDuringWrite) {
      rotateDuringWrite = false;
      auth.token = 'account-C';
      auth.epoch++;
      if (replacementDuringWrite !== null) {
        stored.set(key, replacementDuringWrite);
        replacementDuringWrite = null;
      }
    }
  },
  removeItem: async key => {
    stored.delete(key);
    if (rotateDuringRemove) {
      rotateDuringRemove = false;
      auth.token = 'account-C';
      auth.epoch++;
      if (replacementDuringRemove !== null) {
        stored.set(key, replacementDuringRemove);
        replacementDuringRemove = null;
      }
    }
  },
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
  if (/^(?:\.\.\/)+auth\/gameforgeAuth$/.test(request)) {
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

test('stale explicit epoch cannot modify or read a saved design', async () => {
  const previousEpoch = auth.epoch;
  auth.epoch++;
  await assert.rejects(custody.saveGalaxyProfile(complete(), previousEpoch), /Stale/);
  await assert.rejects(custody.loadGalaxyProfile(previousEpoch), /Stale/);
  await assert.rejects(custody.clearSavedGalaxyProfile(previousEpoch), /Stale/);
});

test('rotating mid-save restores the previous profile without leaking to the next account', async () => {
  auth.token = 'account-A';
  auth.epoch++;
  await custody.saveGalaxyProfile({ ...complete(), title: 'Preserved design' });
  rotateDuringWrite = true;
  await assert.rejects(custody.saveGalaxyProfile({ ...complete(), title: 'Interrupted design' }), /Account changed/);
  assert.equal(await custody.loadGalaxyProfile(), null);
  auth.token = 'account-A';
  auth.epoch++;
  assert.equal((await custody.loadGalaxyProfile()).config.title, 'Preserved design');
});


test('account rotation during clear restores the prior snapshot', async () => {
  auth.token = 'account-A'; auth.epoch++;
  await custody.saveGalaxyProfile({ ...complete(), title: 'Keep this design' });
  rotateDuringRemove = true;
  await assert.rejects(custody.clearSavedGalaxyProfile(), /Account changed/);
  assert.equal(await custody.loadGalaxyProfile(), null);
  auth.token = 'account-A'; auth.epoch++;
  assert.equal((await custody.loadGalaxyProfile()).config.title, 'Keep this design');
});

test('stale save or clear cannot overwrite a replacement already observed in storage', async () => {
  const snapshots = load('src/skeletonForge/galaxyProfileSnapshot.ts');
  auth.token = 'account-A'; auth.epoch++;
  await custody.saveGalaxyProfile({ ...complete(), title: 'Before' });
  replacementDuringWrite = JSON.stringify(snapshots.makeSavedGalaxyProfile({ ...complete(), title: 'Concurrent save' }));
  rotateDuringWrite = true;
  await assert.rejects(custody.saveGalaxyProfile({ ...complete(), title: 'Stale save' }), /Account changed/);
  auth.token = 'account-A'; auth.epoch++;
  assert.equal((await custody.loadGalaxyProfile()).config.title, 'Concurrent save');
  replacementDuringRemove = JSON.stringify(snapshots.makeSavedGalaxyProfile({ ...complete(), title: 'Concurrent replacement' }));
  rotateDuringRemove = true;
  await assert.rejects(custody.clearSavedGalaxyProfile(), /Account changed/);
  auth.token = 'account-A'; auth.epoch++;
  assert.equal((await custody.loadGalaxyProfile()).config.title, 'Concurrent replacement');
});

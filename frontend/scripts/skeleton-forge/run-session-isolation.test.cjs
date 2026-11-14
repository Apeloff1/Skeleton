'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const { load } = require('./harness.cjs');

const originalLoad = Module._load;
let hooks;
try {
  // No authentication data or network is accessed by this pure contract test.
  Module._load = function isolateRunSources(request, parent, isMain) {
    if (request === '../auth/gameforgeAuth') {
      return { getAuthEpoch: () => 10, subscribeAuthChanges: () => () => {} };
    }
    if (request === './client') {
      return { composeVision() {}, errorText() {}, fetchBeats() {}, fetchEras() {},
        fetchGenerations() {}, runForge() {} };
    }
    return originalLoad.call(this, request, parent, isMain);
  };
  hooks = load('src/skeletonForge/hooks.ts');
} finally {
  Module._load = originalLoad;
}

test('late result acceptance requires the original account, request and live signal', () => {
  const isCurrent = hooks.currentForgeRun;
  assert.equal(isCurrent(10, 10, 12, 12, false), true);
  for (const args of [
    [10, 11, 12, 12, false], // account changed
    [10, 10, 12, 13, false], // new run superseded old
    [10, 10, 12, 12, true],  // explicit cancellation
    [10, 11, 12, 13, true],  // all three stale
  ]) assert.equal(isCurrent(...args), false);
});

test('the active hook clears private project files on auth epoch change', () => {
  const src = fs.readFileSync(
    path.resolve(__dirname, '../../src/skeletonForge/hooks.ts'), 'utf8',
  );
  assert.match(src, /subscribeAuthChanges\(invalidate\)/);
  assert.match(src, /ctrlRef\.current\?\.abort\(\)/);
  assert.match(src, /requestIdRef\.current \+= 1/);
  assert.match(src, /setState\(emptyForgeRun\(\)\)/);
  assert.match(src, /currentForgeRun\(startedEpoch, getAuthEpoch\(\), requestId/);
  assert.match(src, /payload: null, request: null, error: null/);
});

test('the device sharing path always clears temporary private ZIP data', () => {
  const src = fs.readFileSync(
    path.resolve(__dirname, '../../src/skeletonForge/shareSourceArchive.ts'), 'utf8',
  );
  assert.match(src, /finally \{\s*try \{ if \(file\.exists\) file\.delete\(\); \}/);
  assert.match(src, /owner|stillCurrent/);
  assert.match(src, /Godot source file checksum mismatch/);
  assert.match(src, /Godot source manifest checksum mismatch/);
  assert.match(src, /Crypto\.randomUUID\(\)/);
  assert.match(src, /if \(file\.exists\) throw new Error/);
  assert.doesNotMatch(src, /if \(file\.exists\) file\.delete\(\);\s*file\.create\(\)/);
});

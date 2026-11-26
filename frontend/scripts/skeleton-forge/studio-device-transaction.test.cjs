'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { compileFunction } = require('node:vm');
const ts = require('typescript');
const { load: real } = require('./harness.cjs');
const ROOT = path.resolve(__dirname, '../..');
function load(relative, imports) {
  const output = ts.transpileModule(fs.readFileSync(path.join(ROOT, relative), 'utf8'), {
    fileName: relative, reportDiagnostics: true,
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true },
  });
  assert.equal(output.diagnostics.length, 0);
  const mod = { exports: {} };
  compileFunction(output.outputText, ['require', 'module', 'exports'])(id => {
    assert.ok(Object.hasOwn(imports, id), 'Unexpected dependency: ' + id);
    return imports[id];
  }, mod, mod.exports);
  return mod.exports;
}
const S = real('src/skeletonForge/foundation/storage.ts');
const F = real('src/skeletonForge/foundation/model.ts');
const at = '2026-11-14T12:00:00.000Z';
function snapshot(title) {
  return { onboarded: true, prefs: F.DEFAULT_PREFS, projectsCorrupt: false, holdSaves: false,
    projects: [{ id: 'p_one', title, createdAt: at, updatedAt: at,
      questionnaire: { ...F.freshQuestionnaire(), vision: title }, lastRun: null }] };
}
function deferred() {
  let resolve; const promise = new Promise(yes => { resolve = yes; });
  return { promise, resolve };
}
function fixture() {
  let epoch = 0, fingerprint = 'a'.repeat(64);
  const rows = new Map();
  const storage = {
    getItem: async key => rows.get(key) ?? null,
    setItem: async (key, value) => { rows.set(key, value); },
    removeItem: async key => { rows.delete(key); },
  };
  const D = load('src/skeletonForge/foundation/storageDevice.ts', {
    '@react-native-async-storage/async-storage': storage,
    '../../auth/gameforgeAuth': { getAuthEpoch: () => epoch },
    '../creatorStorageScope': { creatorStorageScope: async prefix => {
      const captured = epoch, owner = fingerprint;
      return { key: prefix + ':' + owner, stillCurrent: () => captured === epoch && owner === fingerprint };
    } },
    './storage': S,
  });
  return { ...D, storage, rows, rotate(next = fingerprint) { epoch++; fingerprint = next; } };
}

test('separate adapters cannot interleave project publication and reading', async () => {
  const f = fixture(), a = f.asyncStorageKv(), b = f.asyncStorageKv();
  await S.loadFoundation(a);
  const entered = deferred(), release = deferred(), set = f.storage.setItem;
  f.storage.setItem = async (key, value) => {
    if (key.startsWith(S.KEYS.projects + ':')) { entered.resolve(); await release.promise; }
    await set(key, value);
  };
  const save = S.saveFoundation(a, snapshot('First'));
  await entered.promise;
  const read = S.loadFoundation(b);
  release.resolve();
  await save;
  assert.equal((await read).projects[0].title, 'First');
});

test('a stale adapter autosave cannot overwrite a newer library', async () => {
  const f = fixture(), a = f.asyncStorageKv(), b = f.asyncStorageKv();
  await S.loadFoundation(a);
  await S.saveFoundation(a, snapshot('Original'));
  await S.loadFoundation(b);
  await S.saveFoundation(a, snapshot('Newer'));
  await assert.rejects(S.saveFoundation(b, snapshot('Stale')), /reload before saving/);
  assert.equal((await S.loadFoundation(b)).projects[0].title, 'Newer');
  await S.saveFoundation(b, snapshot('After reload'));
  assert.equal((await S.loadFoundation(a)).projects[0].title, 'After reload');
});

test('same-owner reentry waits for stale write rollback', async () => {
  const f = fixture(), a = f.asyncStorageKv();
  await S.loadFoundation(a);
  await S.saveFoundation(a, snapshot('Prior'));
  const entered = deferred(), release = deferred(), set = f.storage.setItem;
  let blocked = false;
  f.storage.setItem = async (key, value) => {
    if (key.startsWith(S.KEYS.projects + ':') && !blocked) {
      blocked = true; entered.resolve(); await release.promise;
    }
    await set(key, value);
  };
  const pending = S.saveFoundation(a, snapshot('Stale'));
  const denied = assert.rejects(pending, /Account changed/);
  await entered.promise;
  f.rotate();
  const fresh = S.loadFoundation(f.asyncStorageKv());
  release.resolve();
  await denied;
  assert.equal((await fresh).projects[0].title, 'Prior');
});

test('uninitialized previous-session adapter cannot bind a new account', async () => {
  const f = fixture(), old = f.asyncStorageKv();
  f.rotate('b'.repeat(64));
  await assert.rejects(S.saveFoundation(old, snapshot('Private')), /Account changed/);
  assert.equal(f.rows.size, 0);
});

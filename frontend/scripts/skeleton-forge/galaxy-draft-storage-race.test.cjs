'use strict';
// Actual production modules with deterministic platform I/O seams.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { compileFunction } = require('node:vm');
const { createHash } = require('node:crypto');
const ts = require('typescript');
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
function deferred() {
  let resolve;
  const promise = new Promise(yes => { resolve = yes; });
  return { promise, resolve };
}
function fixture() {
  let epoch = 0, token = 'local-fixture-a';
  const rows = new Map();
  const owner = {
    getAuthEpoch: () => epoch, getAuthToken: () => token,
    initializeStoredToken: async () => {},
  };
  const storage = {
    getItem: async key => rows.get(key) ?? null,
    setItem: async (key, value) => { rows.set(key, value); },
    removeItem: async key => { rows.delete(key); },
  };
  const scope = load('src/skeletonForge/creatorStorageScope.ts', {
    'expo-crypto': { CryptoDigestAlgorithm: { SHA256: 'SHA256' },
      digestStringAsync: async (_, value) => createHash('sha256').update(value).digest('hex') },
    '../auth/gameforgeAuth': owner,
  });
  const codec = load('src/features/GalaxyStudioFactory/galaxyDraftCodec.ts', {});
  const draft = load('src/features/GalaxyStudioFactory/draftCustody.ts', {
    '@react-native-async-storage/async-storage': storage, './galaxyDraftCodec': codec,
    '../../skeletonForge/creatorStorageScope': scope, '../../auth/gameforgeAuth': owner,
  });
  return { ...draft, scope, storage, rows, owner,
    rotate(next = token) { token = next; epoch++; },
    snapshot(title) { return codec.normalizeGalaxyDraft({ schema: codec.GALAXY_DRAFT_SCHEMA, savedMs: Date.now(), title }); },
  };
}

test('same namespace writes are serialized and newest submitted snapshot wins', async () => {
  const f = fixture(), entered = deferred(), resume = deferred();
  const original = f.storage.setItem;
  let calls = 0;
  f.storage.setItem = async (key, value) => {
    if (++calls === 1) { entered.resolve(); await resume.promise; }
    await original(key, value);
  };
  const first = f.saveGalaxyDraft(f.snapshot('First'));
  await entered.promise;
  const second = f.saveGalaxyDraft(f.snapshot('Second'));
  const read = f.loadGalaxyDraft();
  resume.resolve();
  await Promise.all([first, second]);
  assert.equal((await read).title, 'Second');
  assert.equal((await f.loadGalaxyDraft()).title, 'Second');
});

test('account change during write restores previous owner draft before same-key reentry', async () => {
  const f = fixture();
  await f.saveGalaxyDraft(f.snapshot('Prior'));
  const entered = deferred(), resume = deferred(), original = f.storage.setItem;
  let calls = 0;
  f.storage.setItem = async (key, value) => {
    if (++calls === 1) { entered.resolve(); await resume.promise; }
    await original(key, value);
  };
  const old = f.saveGalaxyDraft(f.snapshot('Stale'));
  const rejection = assert.rejects(old, /Account changed/);
  await entered.promise;
  f.rotate();
  const read = f.loadGalaxyDraft();
  resume.resolve();
  await rejection;
  assert.equal((await read).title, 'Prior');
  await f.saveGalaxyDraft(f.snapshot('Replacement'));
  assert.equal((await f.loadGalaxyDraft()).title, 'Replacement');
});

test('stale scope cannot switch namespace during cold initialization', async () => {
  const f = fixture(), entered = deferred(), resume = deferred();
  f.owner.initializeStoredToken = async () => { entered.resolve(); await resume.promise; };
  const pending = f.scope.creatorStorageScope('@skeleton_galaxy_editor_draft_v1');
  const rejection = assert.rejects(pending, /Account changed/);
  await entered.promise;
  f.rotate('local-fixture-b');
  resume.resolve();
  await rejection;
});

test('invalid record cleanup cannot remove a changed value', async () => {
  const f = fixture();
  const scoped = await f.scope.creatorStorageScope('@skeleton_galaxy_editor_draft_v1');
  f.rows.set(scoped.key, '{bad');
  const get = f.storage.getItem;
  let reads = 0;
  const replacement = JSON.stringify(f.snapshot('Preserved'));
  f.storage.getItem = async key => {
    if (++reads === 2) f.rows.set(key, replacement);
    return get(key);
  };
  assert.equal(await f.loadGalaxyDraft(), null);
  assert.equal(f.rows.get(scoped.key), replacement);
});

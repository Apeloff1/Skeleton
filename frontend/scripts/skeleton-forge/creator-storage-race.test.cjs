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
  let epoch = 0;
  const rows = new Map();
  const owner = { getAuthEpoch: () => epoch };
  const scope = { creatorStorageScope: async key => {
    const captured = epoch;
    return { key, stillCurrent: () => captured === epoch };
  } };
  const storage = {
    getItem: async key => rows.get(key) ?? null,
    setItem: async (key, value) => { rows.set(key, value); },
    removeItem: async key => { rows.delete(key); },
  };
  const schema = 'skeleton.creator.handoff.v1';
  const bridge = load('src/skeletonForge/creatorBridgeStorage.ts', {
    '@react-native-async-storage/async-storage': storage,
    '../auth/gameforgeAuth': owner, './creatorStorageScope': scope,
    './creatorBridge': { CREATOR_BRIDGE_SCHEMA: schema, CREATOR_BRIDGE_MAX_CHARS: 500000,
      parseCreatorBridge: (raw, target) => raw?.schema === schema && raw.target === target ? { ...raw } : null },
  });
  const presets = load('src/skeletonForge/designPresetStorage.ts', {
    '@react-native-async-storage/async-storage': storage,
    '../auth/gameforgeAuth': owner, './creatorStorageScope': scope,
    './designPresets': { DESIGN_PRESET_STORAGE_KEY: 'presets',
      decodeDesignPresets: raw => raw === null ? [] : JSON.parse(raw),
      encodeDesignPresets: items => JSON.stringify(items) },
  });
  return { ...bridge, ...presets, rows, storage, rotate() { epoch++; },
    epoch: () => epoch, draft: vision => ({ schema, target: 'forge', vision }) };
}

test('stale creator write restores prior envelope under the same namespace queue', async () => {
  const f = fixture();
  await f.storeCreatorBridge(f.draft('Prior'));
  const entered = deferred(), resume = deferred(), original = f.storage.setItem;
  let calls = 0;
  f.storage.setItem = async (key, value) => {
    if (++calls === 1) { entered.resolve(); await resume.promise; }
    await original(key, value);
  };
  const pending = f.storeCreatorBridge(f.draft('Stale'));
  const denied = assert.rejects(pending, /Account changed/);
  await entered.promise;
  f.rotate();
  const consumer = f.consumeCreatorBridge('forge');
  resume.resolve();
  await denied;
  assert.equal((await consumer).vision, 'Prior');
  assert.equal(await f.consumeCreatorBridge('forge'), null);
});

test('rotation during uncommitted consume retains valid handoff', async () => {
  const f = fixture();
  await f.storeCreatorBridge(f.draft('Recover'));
  const entered = deferred(), resume = deferred(), original = f.storage.removeItem;
  f.storage.removeItem = async key => { entered.resolve(); await resume.promise; await original(key); };
  const pending = f.consumeCreatorBridge('forge');
  const denied = assert.rejects(pending, /Account changed/);
  await entered.promise;
  f.rotate();
  resume.resolve();
  await denied;
  f.storage.removeItem = original;
  assert.equal((await f.consumeCreatorBridge('forge')).vision, 'Recover');
});

test('failed Studio receiver commit preserves source until successful acknowledgement', async () => {
  const f = fixture();
  await f.storeCreatorBridge({ ...f.draft('Studio'), target: 'studio' });
  await assert.rejects(f.withCreatorBridge('studio', async () => { throw Error('disk failure'); }), /disk failure/);
  assert.equal(await f.withCreatorBridge('studio', async draft => draft.vision), 'Studio');
  assert.equal(await f.withCreatorBridge('studio', async () => assert.fail('double consume')), null);
});

test('replaced malformed record is not deleted by stale cleanup', async () => {
  const f = fixture(), key = '@skeleton_creator_bridge_v1';
  f.rows.set(key, '{bad');
  const original = f.storage.getItem;
  let reads = 0;
  f.storage.getItem = async key => {
    if (++reads === 2) f.rows.set(key, JSON.stringify(f.draft('New')));
    return original(key);
  };
  await assert.rejects(f.consumeCreatorBridge('forge'), /changed during publication/);
  assert.equal(JSON.parse(f.rows.get(key)).vision, 'New');
});

test('oversized creator cleanup preserves a replacement for both consumer paths', async () => {
  for (const mode of ['consume', 'commit']) {
    const f = fixture(), key = '@skeleton_creator_bridge_v1';
    f.rows.set(key, 'x'.repeat(500001));
    const original = f.storage.getItem;
    let reads = 0;
    f.storage.getItem = async current => {
      if (++reads === 2) f.rows.set(current, JSON.stringify(f.draft('Replacement')));
      return original(current);
    };
    const operation = mode === 'consume' ? f.consumeCreatorBridge('forge')
      : f.withCreatorBridge('forge', async () => assert.fail('oversized input cannot reach the receiver'));
    await assert.rejects(operation, /changed during publication/);
    assert.equal(JSON.parse(f.rows.get(key)).vision, 'Replacement');
  }
});

test('preset rollback preserves previous owner library before reopening the same scope', async () => {
  const f = fixture();
  const lease = await f.openDesignPresetLease(f.epoch());
  await lease.update(() => [{ name: 'Prior' }]);
  const entered = deferred(), resume = deferred(), original = f.storage.setItem;
  let calls = 0;
  f.storage.setItem = async (key, value) => {
    if (++calls === 1) { entered.resolve(); await resume.promise; }
    await original(key, value);
  };
  const pending = lease.update(() => [{ name: 'Stale' }]);
  const denied = assert.rejects(pending, /account changed/);
  await entered.promise;
  f.rotate();
  const fresh = await f.openDesignPresetLease(f.epoch());
  const read = fresh.read();
  resume.resolve();
  await denied;
  assert.deepEqual(await read, [{ name: 'Prior' }]);
});

test('preset rollback never overwrites a replacement already observed in storage', async () => {
  const f = fixture();
  const lease = await f.openDesignPresetLease(f.epoch());
  await lease.update(() => [{ name: 'Prior' }]);
  const original = f.storage.setItem;
  f.storage.setItem = async (key, value) => {
    await original(key, value);
    f.rows.set(key, JSON.stringify([{ name: 'Peer replacement' }]));
    f.rotate();
  };
  await assert.rejects(lease.update(() => [{ name: 'Stale' }]), /account changed/);
  const fresh = await f.openDesignPresetLease(f.epoch());
  assert.deepEqual(await fresh.read(), [{ name: 'Peer replacement' }]);
});

'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const source = fs.readFileSync(path.join(__dirname, '../utils/safeStorage.ts'), 'utf8');
const transpiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020,
    esModuleInterop: true }, reportDiagnostics: true,
});
assert.equal(transpiled.diagnostics.length, 0);
function fixture(overrides = {}) {
  const map = new Map();
  let reads = 0;
  const store = {
    getItem: async key => { reads++; return map.get(key) ?? null; },
    setItem: async (key, value) => { map.set(key, value); },
    removeItem: async key => { map.delete(key); },
    multiRemove: async keys => { for (const key of keys) map.delete(key); },
    getAllKeys: async () => [...map.keys()],
    multiGet: async keys => keys.map(k => [k, map.get(k) ?? null]),
    ...overrides,
  };
  class Fence {
    run(_keys, fn) { return Promise.resolve().then(fn).then(() => true, () => false); }
    isBusy() { return false; }
    pauseAndDrain() { return Promise.resolve(); }
    resume() {}
  }
  const module = { exports: {} };
  new Function('require','module','exports',transpiled.outputText)(id => {
    if (id === '@react-native-async-storage/async-storage') return store;
    if (id === './NativeMutationFence') return { NativeMutationFence: Fence };
    if (id === './storageRetentionPolicy') return { isPrunableStorageKey: () => false };
    throw new Error('Unexpected import '+id);
  }, module, module.exports);
  return { store, map, memory: module.exports, get reads() { return reads; } };
}
test('one enormous native value cannot fill the in-process storage mirror', async () => {
  const f = fixture();
  const large = 'x'.repeat(1024 * 1024);
  assert.equal(await f.memory.safeSetItem('big', large), true);
  assert.equal(f.memory.safeStorageMirrorStats().entries, 0);
  assert.equal(f.map.get('big'), large);
  assert.equal(await f.memory.safeGetItem('big'), large);
  assert.equal(f.memory.safeStorageMirrorStats().entries, 0);
});
test('replacing cached values updates accounting without phantom memory', async () => {
  const f = fixture();
  await f.memory.safeSetItem('theme', 'x'.repeat(30_000));
  assert.equal(f.memory.safeStorageMirrorStats().chars, 30_000);
  await f.memory.safeSetItem('theme', 'y'.repeat(100));
  assert.equal(f.memory.safeStorageMirrorStats().chars, 100);
  await f.memory.safeRemoveItem('theme');
  assert.equal(f.memory.safeStorageMirrorStats().chars, 0);
});
test('many small storage values have both count and aggregate size bounds', async () => {
  const f = fixture();
  const payload = 'x'.repeat(3_000);
  for (let i = 0; i < 650; i++) await f.memory.safeSetItem('key:' + i, payload);
  const stats = f.memory.safeStorageMirrorStats();
  assert.ok(stats.entries <= 650);
  assert.ok(stats.chars <= stats.maxChars);
  assert.ok(stats.chars >= 100_000);
});
test('OS-pressure shedding retains native values but drops in-memory replicas', async () => {
  const f = fixture();
  await f.memory.safeSetItem('a', 'saved');
  assert.equal(f.memory.safeStorageMirrorStats().entries, 1);
  f.memory.shedSafeStorageMirror();
  assert.deepEqual(f.memory.safeStorageMirrorStats(), {
    entries: 0, chars: 0, maxChars: 1024 * 1024,
  });
  assert.equal(await f.memory.safeGetItem('a'), 'saved');
});
test('a late native read cannot repopulate a mirror cleared under pressure', async () => {
  let release;
  const f = fixture({
    getItem: () => new Promise(resolve => { release = resolve; }),
  });
  const before = f.memory.safeGetItem('value', null, 1_000);
  f.memory.shedSafeStorageMirror();
  release('stale');
  assert.equal(await before, null);
  assert.equal(f.memory.safeStorageMirrorStats().entries, 0);
});
test('storage key version rollover releases stale mirror payloads', async () => {
  const f = fixture();
  await f.memory.safeSetItem('original', 'x'.repeat(500));
  for (let i = 0; i < 4_110; i++) await f.memory.safeSetItem('roll:' + i, 'x');
  assert.ok(f.memory.safeStorageMirrorStats().entries <= 2048);
  assert.ok(f.memory.safeStorageMirrorStats().chars <= 1024 * 1024);
});

'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');

const ROOT = path.resolve(__dirname, '..');
function loadTS(file, mocks = {}) {
  const output = ts.transpileModule(fs.readFileSync(path.join(ROOT, file), 'utf8'), {
    fileName: file, compilerOptions: {
      module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, esModuleInterop: true,
    }, reportDiagnostics: true,
  });
  assert.equal(output.diagnostics.length, 0, file + ' syntax');
  const module = { exports: {} };
  new Function('require', 'module', 'exports', output.outputText)(
    id => {
      assert.ok(Object.hasOwn(mocks, id), file + ': missing mock ' + id);
      return mocks[id];
    }, module, module.exports,
  );
  return module.exports;
}
function makeStorage() {
  const map = new Map();
  const storage = {
    getItem: async key => map.get(key) ?? null,
    setItem: async (key, value) => { map.set(key, value); },
    removeItem: async key => { map.delete(key); },
    getAllKeys: async () => [...map.keys()],
    multiRemove: async keys => { for (const key of keys) map.delete(key); },
  };
  return { map, storage };
}
function manifest(collections = { books: 120 }) {
  return {
    collections, version: '2026-SOTA-v2', cacheable: true,
    total_documents: Object.values(collections).reduce((sum, count) => sum + count, 0),
  };
}
function http(data, ok = true) {
  return {
    ok, headers: { get: () => null },
    text: async () => JSON.stringify(data),
  };
}
function mockNetwork(m, opts = {}) {
  const calls = [];
  const fetcher = async (url, init) => {
    calls.push({ url, init });
    if (opts.fail && opts.fail(url, calls.length)) throw new Error('offline');
    if (url.endsWith('/manifest')) return http(m);
    const match = /\/dump\/([^?]+)\?skip=(\d+)&limit=(\d+)/.exec(url);
    assert.ok(match, 'expected paginated dump request');
    const [, name, skipRaw, limitRaw] = match;
    const count = m.collections[decodeURIComponent(name)];
    const skip = Number(skipRaw);
    const limit = Number(limitRaw);
    if (opts.truncate && skip === 100) {
      return http({ documents: Array.from({ length: 10 }, (_, i) => i), has_more: false });
    }
    return http({
      documents: Array.from({ length: Math.max(0, Math.min(limit, count - skip)) }, (_, i) => ({
        id: skip + i, name,
      })),
      has_more: skip + limit < count,
    });
  };
  return { fetcher, calls };
}
function service(storage) {
  return loadTS('services/offlineCache.ts', {
    '../utils/apiBase': { API_BASE: 'https://academy.test' },
    '@react-native-async-storage/async-storage': storage,
  });
}
const settle = () => new Promise(resolve => setImmediate(resolve));

test('successful sync commits manifest only after every page and metadata row', async () => {
  const { map, storage } = makeStorage();
  const app = service(storage);
  const previous = global.fetch;
  const net = mockNetwork(manifest());
  global.fetch = net.fetcher;
  try {
    const progress = [];
    assert.equal(await app.isCacheValid(), false);
    const result = await app.syncAllOfflineData(update => progress.push(update.docProgress.downloaded));
    assert.deepEqual(result, { success: true, collections: 1, documents: 120 });
    assert.deepEqual(progress, [100, 120]);
    assert.equal(await app.isCacheValid(), true);
    assert.equal((await app.getCachedCollection('books')).length, 120);
    assert.deepEqual((await app.getCachedCollectionPage('books', 95, 20)).map(x => x.id),
      Array.from({ length: 20 }, (_, i) => 95 + i));
    assert.ok(map.has('@tutolage_offline_commit:v1'));
    const writeKey = JSON.parse(map.get('@tutolage_offline_commit:v1')).generation;
    assert.ok(map.has('@tutolage_offline_g-' + writeKey + '/books_meta'));
    assert.equal(net.calls.length, 3);
  } finally { global.fetch = previous; }
});

test('truncated page is not published as a successful offline generation', async () => {
  const { map, storage } = makeStorage();
  const app = service(storage);
  const previous = global.fetch;
  global.fetch = mockNetwork(manifest(), { truncate: true }).fetcher;
  try {
    const result = await app.syncAllOfflineData();
    assert.equal(result.success, false);
    assert.equal(await app.isCacheValid(), false);
    assert.equal(map.has('@tutolage_offline_commit:v1'), false);
  } finally { global.fetch = previous; }
});

test('failed replacement leaves previously committed offline pages readable', async () => {
  const { storage } = makeStorage();
  const app = service(storage);
  const previous = global.fetch;
  try {
    global.fetch = mockNetwork(manifest({ books: 2 })).fetcher;
    assert.equal((await app.syncAllOfflineData()).success, true);
    const before = await app.getCachedCollection('books');
    global.fetch = mockNetwork(manifest({ books: 120 }), { truncate: true }).fetcher;
    assert.equal((await app.syncAllOfflineData()).success, false);
    assert.equal(await app.isCacheValid(), true);
    assert.deepEqual(await app.getCachedCollection('books'), before);
    assert.equal((await app.getCachedManifest()).total_documents, 2);
  } finally { global.fetch = previous; }
});

test('a native storage failure during staging cannot publish a new commit', async () => {
  const { map, storage } = makeStorage();
  const write = storage.setItem;
  storage.setItem = async (key, value) => {
    if (key.endsWith('_1')) throw new Error('storage full');
    return write(key, value);
  };
  const app = service(storage);
  const previous = global.fetch;
  global.fetch = mockNetwork(manifest()).fetcher;
  try {
    assert.equal((await app.syncAllOfflineData()).success, false);
    assert.equal(map.has('@tutolage_offline_commit:v1'), false);
  } finally { global.fetch = previous; }
});

test('malformed manifests reject traversal, noninteger counts and inconsistent totals', async () => {
  const { storage } = makeStorage();
  const app = service(storage);
  const previous = global.fetch;
  try {
    for (const bad of [
      manifest({ '../secret': 1 }),
      manifest({ books: -1 }),
      { ...manifest({ books: 2 }), total_documents: 42 },
      manifest({ books: Number.POSITIVE_INFINITY }),
    ]) {
      global.fetch = async () => http(bad);
      assert.equal(await app.fetchManifest(), null);
      assert.equal((await app.syncAllOfflineData()).success, false);
    }
    assert.equal(await app.isCacheValid(), false);
  } finally { global.fetch = previous; }
});

test('simultaneous sync invocations share one authoritative transaction', async () => {
  const { storage } = makeStorage();
  const app = service(storage);
  const prev = global.fetch;
  const net = mockNetwork(manifest({ books: 1 }));
  global.fetch = net.fetcher;
  try {
    const first = app.syncAllOfflineData();
    const second = app.syncAllOfflineData();
    assert.equal(first, second);
    assert.equal((await first).success, true);
    assert.equal(net.calls.length, 2);
  } finally { global.fetch = prev; }
});

test('cancelled staging fails closed and retains the old generation', async () => {
  const { storage } = makeStorage();
  const app = service(storage);
  const previous = global.fetch;
  try {
    global.fetch = mockNetwork(manifest({ books: 3 })).fetcher;
    assert.equal((await app.syncAllOfflineData()).success, true);
    const before = await app.getCachedCollection('books');
    const controller = new AbortController();
    const net = mockNetwork(manifest({ books: 120 }));
    global.fetch = async (url, init) => {
      if (String(url).includes('/dump/')) {
        controller.abort();
        throw new Error('Cancelled');
      }
      return net.fetcher(url, init);
    };
    const result = await app.syncAllOfflineData(undefined, { signal: controller.signal });
    assert.equal(result.success, false);
    assert.deepEqual(await app.getCachedCollection('books'), before);
  } finally { global.fetch = previous; }
});

test('clear waits for active sync and does not allow a late commit', async () => {
  const { map, storage } = makeStorage();
  const app = service(storage);
  const prev = global.fetch;
  let unblock;
  const net = mockNetwork(manifest({ books: 1 }));
  global.fetch = (url, init) => {
    if (url.endsWith('/manifest')) return net.fetcher(url, init);
    return new Promise(resolve => { unblock = () => resolve(http({ documents: [{ id: 1 }], has_more: false })); });
  };
  try {
    const pending = app.syncAllOfflineData();
    await settle();
    const clearing = app.clearOfflineCache();
    const failed = await pending;
    assert.equal(failed.success, false);
    await clearing;
    if (unblock) unblock();
    await settle();
    assert.equal(await app.isCacheValid(), false);
    assert.equal(map.size, 0);
  } finally { global.fetch = prev; }
});

test('old malformed commit cannot silently authorize legacy fallback', async () => {
  const { storage, map } = makeStorage();
  map.set('@tutolage_offline_commit:v1', '{"version":"forged"}');
  map.set('@tutolage_cache_version', '2026-SOTA-v2');
  map.set('@tutolage_manifest', JSON.stringify(manifest({ books: 1 })));
  const app = service(storage);
  assert.equal(await app.isCacheValid(), false);
  assert.equal(await app.getCachedManifest(), null);
});

test('large collections require paged reads instead of enormous array accumulation', async () => {
  const { storage } = makeStorage();
  const app = service(storage);
  const previous = global.fetch;
  global.fetch = mockNetwork(manifest({ books: 20001 })).fetcher;
  try {
    assert.equal((await app.syncAllOfflineData()).success, true);
    assert.deepEqual(await app.getCachedCollection('books'), []);
    assert.equal((await app.getCachedCollectionPage('books', 20000, 10)).length, 1);
  } finally { global.fetch = previous; }
});

test('legacy 200-row chunks remain accessible after the transactional upgrade', async () => {
  const { storage, map } = makeStorage();
  const app = service(storage);
  const m = manifest({ books: 250 });
  map.set('@tutolage_cache_version', '2026-SOTA-v2');
  map.set('@tutolage_manifest', JSON.stringify(m));
  map.set('@tutolage_offline_books_meta',
    JSON.stringify({ total: 250, chunks: 2, cachedAt: new Date().toISOString() }));
  map.set('@tutolage_offline_books_0', JSON.stringify(
    Array.from({ length: 200 }, (_, i) => ({ id: i }))));
  map.set('@tutolage_offline_books_1', JSON.stringify(
    Array.from({ length: 50 }, (_, i) => ({ id: i + 200 }))));
  assert.equal(await app.isCacheValid(), true);
  const page = await app.getCachedCollectionPage('books', 190, 30);
  assert.deepEqual(page.map(row => row.id), Array.from({ length: 30 }, (_, i) => 190 + i));
  assert.equal((await app.getCachedCollection('books')).length, 250);
});

test('corrupt missing chunks fail closed instead of returning partial collections', async () => {
  const { storage, map } = makeStorage();
  const app = service(storage);
  const oldFetch = global.fetch;
  global.fetch = mockNetwork(manifest({ books: 120 })).fetcher;
  try {
    assert.equal((await app.syncAllOfflineData()).success, true);
    const committed = JSON.parse(map.get('@tutolage_offline_commit:v1'));
    map.delete('@tutolage_offline_g-' + committed.generation + '/books_1');
    assert.deepEqual(await app.getCachedCollection('books'), []);
    assert.deepEqual(await app.getCachedCollectionPage('books', 100, 20), []);
  } finally { global.fetch = oldFetch; }
});

test('a fetch shim that ignores AbortSignal cannot prevent clear from settling', async () => {
  const { storage } = makeStorage();
  const app = service(storage);
  const oldFetch = global.fetch;
  let called = 0;
  global.fetch = async url => {
    called++;
    if (String(url).endsWith('/manifest')) return http(manifest({ books: 1 }));
    return new Promise(() => {}); // invalid native adapter: never settles
  };
  try {
    const work = app.syncAllOfflineData();
    await settle();
    const clear = app.clearOfflineCache();
    const result = await Promise.race([
      work, new Promise((_resolve, reject) => setTimeout(() => reject(new Error('hung')), 1200)),
    ]);
    assert.equal(result.success, false);
    await clear;
    assert.equal(await app.isCacheValid(), false);
    assert.equal(called, 2);
  } finally { global.fetch = oldFetch; }
});

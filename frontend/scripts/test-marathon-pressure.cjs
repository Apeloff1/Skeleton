'use strict';
const { compileFunction } = require('node:vm');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');

const ROOT = path.resolve(__dirname, '..');
function loadTS(filename, mocks = {}) {
  const output = ts.transpileModule(fs.readFileSync(path.join(ROOT, filename), 'utf8'), {
    fileName: filename,
    compilerOptions: {
      module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020,
      esModuleInterop: true,
    },
    reportDiagnostics: true,
  });
  assert.equal((output.diagnostics || []).length, 0, filename + ' syntax');
  const mod = { exports: {} };
  compileFunction(output.outputText, ['require', 'module', 'exports'])(
    id => {
      if (id === './requestRecoveryPolicy') return loadTS('src/utils/requestRecoveryPolicy.ts');
      assert.ok(Object.hasOwn(mocks, id), filename + ' unexpected import ' + id);
      return mocks[id];
    },
    mod, mod.exports,
  );
  return mod.exports;
}
const settle = () => new Promise(resolve => setImmediate(resolve));
function net(storage = null, urls = ['https://primary.test', 'https://backup.test']) {
  return loadTS('src/utils/resilientNet.ts', {
    '@react-native-async-storage/async-storage': storage || {
      getItem: async () => null, setItem: async () => {},
    },
    './apiBase': { API_BASE: urls[0], API_FALLBACK_BASE: urls[1] },
  });
}
function reply(data, options = {}) {
  return {
    ok: true, status: 200,
    headers: { get: () => null },
    text: async () => typeof data === 'string' ? data : JSON.stringify(data),
    ...options,
  };
}

test('duplicate mutation keys execute separately by default', async t => {
  const { ThermalGuard } = loadTS('src/utils/thermalGuard.ts');
  const guard = new ThermalGuard();
  t.after(() => guard.destroy());
  let effects = 0;
  const work = () => guard.fetch('write:session', async () => ++effects);
  const result = await Promise.all([work(), work(), work()]);
  assert.deepEqual(result, [1, 2, 3]);
  assert.equal(effects, 3);
});

test('explicit read-only coalescing shares a single in-flight request', async t => {
  const { ThermalGuard } = loadTS('src/utils/thermalGuard.ts');
  const guard = new ThermalGuard();
  t.after(() => guard.destroy());
  let effects = 0;
  const work = () => guard.fetch('read:inventory', async () => ++effects, {
    dedupe: true, cacheTtlMs: 1000,
  });
  const results = await Promise.all([work(), work(), work()]);
  assert.deepEqual(results, [1, 1, 1]);
  assert.equal(effects, 1);
  assert.equal(await work(), 1);
});

test('thermal cache enforces entry budget and refuses invalid TTL values', t => {
  const { ThermalGuard } = loadTS('src/utils/thermalGuard.ts');
  const guard = new ThermalGuard();
  t.after(() => guard.destroy());
  guard.cache.set('oversized', 'x'.repeat(150 * 1024), 60_000);
  assert.equal(guard.cache.get('oversized'), null);
  guard.cache.set('invalid', 'anything', Number.POSITIVE_INFINITY);
  assert.equal(guard.cache.get('invalid'), null);
  for (let i = 0; i < 110; i++) {
    guard.cache.set('small:' + i, 'ok', 60_000);
  }
  assert.ok(guard.cache.size <= 100);
  assert.ok(guard.cache.bytesApproximate <= 8 * 1024 * 1024);
  guard.cache.clear();
  assert.equal(guard.cache.bytesApproximate, 0);
});

test('thermal observers cannot crash peer listeners and guard destroy prevents new tasks', async () => {
  const { ThermalGuard } = loadTS('src/utils/thermalGuard.ts');
  const guard = new ThermalGuard();
  let notifications = 0;
  guard.subscribe(() => { throw new Error('bad consumer'); });
  guard.subscribe(() => { notifications++; });
  guard.setBattery(0.01, false);
  assert.ok(notifications >= 1);
  guard.destroy();
  guard.destroy();
  await assert.rejects(guard.fetch('new', async () => 5), /destroyed/);
  await assert.rejects(guard.queue.enqueue('new', async () => 5), /destroyed/);
});

test('thermal activity pressure recomputes during a sustained event burst', t => {
  const { ThermalGuard } = loadTS('src/utils/thermalGuard.ts');
  const guard = new ThermalGuard();
  t.after(() => guard.destroy());
  const original = Date.now;
  let now = 2_000_000_000_000;
  Date.now = () => now;
  try {
    for (let i = 0; i < 99; i++) guard.recordActivity();
    now += 1001;
    guard.recordActivity();
    assert.equal(guard.getState().level, 'warm');
  } finally {
    Date.now = original;
  }
});

test('custom-header GET never forwards its headers to a backup host', async () => {
  const client = net();
  const original = global.fetch;
  const urls = [];
  global.fetch = async url => { urls.push(url); throw new Error('offline'); };
  try {
    await assert.rejects(client.rget('/private', {
      headers: { Authorization: 'Bearer token' }, retries: 0, cacheTtlMs: 0,
    }), /1 host/);
    assert.deepEqual(urls, ['https://primary.test/private']);
  } finally {
    global.fetch = original;
    client.stopHeartbeat();
  }
});

test('custom request headers isolate cache even if not credentials', async () => {
  const client = net();
  const original = global.fetch;
  let requests = 0;
  global.fetch = async () => reply({ count: ++requests });
  try {
    const first = await client.rget('/localized', { headers: { 'Accept-Language': 'en' } });
    const second = await client.rget('/localized', { headers: { 'Accept-Language': 'fr' } });
    assert.equal(first.data.count, 1);
    assert.equal(second.data.count, 2);
    assert.equal(second.fromCache, false);
  } finally {
    global.fetch = original;
    client.stopHeartbeat();
  }
});

test('raw and decoded responses are never coalesced into a mismatched type', async () => {
  const client = net();
  const original = global.fetch;
  let resolveFirst, resolveSecond;
  let count = 0;
  global.fetch = () => new Promise(resolve => {
    count++;
    if (count === 1) resolveFirst = resolve;
    else resolveSecond = resolve;
  });
  try {
    const json = client.rget('/same', { cacheTtlMs: 0, retries: 0 });
    const raw = client.rget('/same', { cacheTtlMs: 0, retries: 0, rawText: true });
    assert.equal(count, 2);
    resolveFirst(reply('{"ok":true}'));
    resolveSecond(reply('{"ok":true}'));
    assert.deepEqual((await json).data, { ok: true });
    assert.equal((await raw).data, '{"ok":true}');
  } finally {
    global.fetch = original;
    client.stopHeartbeat();
  }
});

test('different response budgets do not share an in-flight promise', async () => {
  const client = net();
  const original = global.fetch;
  let count = 0;
  const resolvers = [];
  global.fetch = () => new Promise(resolve => {
    count++;
    resolvers.push(resolve);
  });
  try {
    const strict = client.rget('/large', { cacheTtlMs: 0, retries: 0, maxResponseChars: 1024 });
    const large = client.rget('/large', { cacheTtlMs: 0, retries: 0, maxResponseChars: 4096 });
    assert.equal(count, 2);
    resolvers[0](reply('x'.repeat(2000)));
    resolvers[1](reply('x'.repeat(2000)));
    await assert.rejects(strict, /Response exceeds size budget/);
    assert.equal((await large).data.length, 2000);
  } finally {
    global.fetch = original;
    client.stopHeartbeat();
  }
});

test('streaming reader rejects over-budget data before calling response.text()', async () => {
  const client = net();
  const original = global.fetch;
  let reads = 0, cancelled = false, textCalled = false;
  global.fetch = async () => reply('', {
    body: {
      getReader: () => ({
        read: async () => { reads++; return { done: false, value: new Uint8Array(3000) }; },
        cancel: async () => { cancelled = true; },
        releaseLock() {},
      }),
    },
    text: async () => { textCalled = true; return 'unused'; },
  });
  try {
    await assert.rejects(client.rget('/stream', {
      maxResponseChars: 1024, cacheTtlMs: 0, retries: 0,
    }), /Response exceeds size budget/);
    assert.equal(reads, 1);
    assert.equal(cancelled, true);
    assert.equal(textCalled, false);
  } finally {
    global.fetch = original;
    client.stopHeartbeat();
  }
});

test('streaming UTF-8 data is decoded across byte boundaries', async () => {
  const client = net();
  const original = global.fetch;
  const bytes = new TextEncoder().encode('{"value":"héllo"}');
  let offset = 0;
  global.fetch = async () => reply('', {
    body: {
      getReader: () => ({
        read: async () => {
          if (offset >= bytes.length) return { done: true };
          const value = bytes.slice(offset, ++offset);
          return { done: false, value };
        },
        releaseLock() {},
      }),
    },
    text: async () => { throw new Error('should stream'); },
  });
  try {
    const value = await client.rget('/utf8', { retries: 0, cacheTtlMs: 0 });
    assert.deepEqual(value.data, { value: 'héllo' });
  } finally {
    global.fetch = original;
    client.stopHeartbeat();
  }
});

test('network cache never holds oversized entries or persists them', async () => {
  const saved = [];
  const client = net({
    getItem: async () => null,
    setItem: async (key, value) => { saved.push({ key, value }); },
  });
  const original = global.fetch;
  global.fetch = async () => reply('x'.repeat(2 * 1024 * 1024));
  try {
    await client.rget('/big', { retries: 0, cacheTtlMs: 30_000 });
    assert.equal(client.getResilientCacheStats().entries, 0);
    await settle();
    assert.equal(saved.length, 0);
  } finally {
    global.fetch = original;
    client.stopHeartbeat();
  }
});

test('cache reset frees tracked memory and makes the next request fetch again', async () => {
  const client = net();
  const original = global.fetch;
  let reads = 0;
  global.fetch = async () => reply({ read: ++reads });
  try {
    await client.rget('/inventory', { retries: 0 });
    assert.equal(client.getResilientCacheStats().entries, 1);
    client.resetCircuit();
    assert.deepEqual(client.getResilientCacheStats(), {
      entries: 0, chars: 0, maxChars: 16 * 1024 * 1024,
    });
    const next = await client.rget('/inventory', { retries: 0 });
    assert.equal(next.fromCache, false);
    assert.equal(next.data.read, 2);
  } finally {
    global.fetch = original;
    client.stopHeartbeat();
  }
});

test('old requests never repopulate cache after an explicit reset', async () => {
  const client = net();
  const original = global.fetch;
  let resolveNetwork;
  global.fetch = () => new Promise(resolve => { resolveNetwork = resolve; });
  try {
    const old = client.rget('/stale', { retries: 0 });
    client.resetCircuit();
    resolveNetwork(reply({ old: true }));
    await old;
    assert.equal(client.getResilientCacheStats().entries, 0);
  } finally {
    global.fetch = original;
    client.stopHeartbeat();
  }
});

test('corrupt and future-dated persistent caches are rejected on fallback', async () => {
  const storage = {
    getItem: async () => JSON.stringify({ data: 'false-success', ts: Date.now() + 3_600_000 }),
    setItem: async () => {},
  };
  const client = net(storage, ['', '']);
  try {
    await assert.rejects(client.rget('/offline', { retries: 0 }), /No backend URL configured/);
  } finally { client.stopHeartbeat(); }
});

test('request generation does not automatically attach idempotency headers', async () => {
  const client = net();
  const original = global.fetch;
  let headers;
  global.fetch = async (_url, opts) => {
    headers = opts.headers;
    return reply({ accepted: true });
  };
  try {
    await client.rpost('/create', { project: 'game' }, { retries: 9 });
    assert.equal(headers['X-Idempotency-Key'], undefined);
  } finally {
    global.fetch = original;
    client.stopHeartbeat();
  }
});

'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { compileFunction } = require('node:vm');
const ts = require('typescript');
const ROOT = path.resolve(__dirname, '..');
function load(file, imports) {
  const compiled = ts.transpileModule(fs.readFileSync(path.join(ROOT, file), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true },
  });
  const module = { exports: {} };
  compileFunction(compiled.outputText, ['require', 'module', 'exports'])(id => {
    assert.ok(Object.hasOwn(imports, id), `${file}: unexpected import ${id}`);
    return imports[id];
  }, module, module.exports);
  return module.exports;
}
const tick = () => new Promise(resolve => setImmediate(resolve));
function deferred() { let resolve; const promise = new Promise(yes => { resolve = yes; }); return { promise, resolve }; }
function fixture(file = 'apiController') {
  let epoch = 0;
  let token = 'account-a';
  let account = new AbortController();
  const listeners = new Set();
  const disk = new Map([['apiController:cache:v1', JSON.stringify({ 'GET https://backend.test/api/private': { body: 'foreign-data', expiresAt: Date.now() + 100000 } })]]);
  const storage = { getItem: async key => disk.get(key) ?? null, setItem: async (key, value) => disk.set(key, value),
    removeItem: async key => { disk.delete(key); }, getAllKeys: async () => [...disk.keys()], multiRemove: async keys => { keys.forEach(key => disk.delete(key)); } };
  const owner = {
    subscribeApiSessionChanges(fn) { listeners.add(fn); return () => listeners.delete(fn); },
    async prepareApiRequest(url, supplied = {}, signal) {
      const admittedEpoch = epoch;
      const controller = new AbortController();
      const active = account.signal;
      const abort = () => controller.abort();
      signal?.addEventListener('abort', abort, { once: true }); active.addEventListener('abort', abort, { once: true });
      if (active.aborted || signal?.aborted) abort();
      const headers = { ...supplied };
      const explicit = Object.keys(headers).some(key => key.toLowerCase() === 'authorization');
      const automatic = token && !explicit && url.startsWith('https://backend.test/api/');
      if (automatic) headers.Authorization = `Bearer ${token}`;
      return { headers, signal: controller.signal, epoch: admittedEpoch, cacheNamespace: `run:${admittedEpoch}`,
        authenticated: Boolean(token || explicit), redirect: automatic ? 'error' : undefined,
        current: () => admittedEpoch === epoch && !controller.signal.aborted,
        dispose() { signal?.removeEventListener('abort', abort); active.removeEventListener('abort', abort); } };
    },
  };
  const imports = { './apiClient': owner, './apiBase': { API_BASE: 'https://backend.test', API_FALLBACK_BASE: 'https://backup.test' },
    'react-native': { Platform: { OS: 'web' } }, '@react-native-async-storage/async-storage': storage,
    './requestRecoveryPolicy': load('src/utils/requestRecoveryPolicy.ts', {}) };
  const transport = load(`src/utils/${file}.ts`, imports);
  return { ...transport, disk, switchAccount(next = 'account-b') { account.abort(); account = new AbortController(); token = next; epoch++; for (const listener of listeners) listener(); } };
}
function response(value) { return new Response(JSON.stringify(value), { status: 200, headers: { 'Content-Type': 'application/json' } }); }

test('legacy controller authenticates cache hits through the current session and retires old disk rows', async t => {
  const f = fixture();
  const previous = global.fetch;
  t.after(() => { global.fetch = previous; });
  const calls = [];
  global.fetch = async (_url, init) => { calls.push(init); return response({ account: init.headers.Authorization }); };
  assert.deepEqual(await f.api.get('/api/private', { cacheTtlMs: 60000 }), { account: 'Bearer account-a' });
  assert.equal(calls[0].redirect, 'error');
  assert.deepEqual(await f.api.get('/api/private', { cacheTtlMs: 60000 }), { account: 'Bearer account-a' });
  assert.equal(calls.length, 1);
  assert.equal(f.disk.has('apiController:cache:v1'), false);
  f.switchAccount();
  assert.deepEqual(await f.api.get('/api/private', { cacheTtlMs: 60000 }), { account: 'Bearer account-b' });
  assert.equal(calls.length, 2);
});

test('drop-in apiFetch cancels and fences responses from fetch adapters ignoring abort', async t => {
  const f = fixture();
  const previous = global.fetch;
  t.after(() => { global.fetch = previous; });
  const pending = deferred(); let requestSignal;
  global.fetch = async (_url, init) => { requestSignal = init.signal; return pending.promise; };
  const request = f.apiFetch('/api/private');
  await tick(); f.switchAccount();
  assert.equal(requestSignal.aborted, true);
  pending.resolve(response({ secret: 'old-account' }));
  await assert.rejects(request, /detached/);
});

test('drop-in apiFetch keeps response body readers fenced and aborts pending body reads', async t => {
  const f = fixture();
  const previous = global.fetch;
  t.after(() => { global.fetch = previous; });
  const pending = deferred(); let requestSignal;
  global.fetch = async (_url, init) => { requestSignal = init.signal; return { ok: true, status: 200, json: () => pending.promise }; };
  const result = await f.apiFetch('/api/private');
  const body = result.json();
  f.switchAccount();
  assert.equal(requestSignal.aborted, true);
  pending.resolve({ secret: 'old-account' });
  await assert.rejects(body, /detached/);
});

test('drop-in apiFetch preserves explicit authorization without sharing account responses', async t => {
  const f = fixture();
  const previous = global.fetch;
  t.after(() => { global.fetch = previous; });
  global.fetch = async (_url, init) => response({ explicit: init.headers.authorization, automatic: init.headers.Authorization });
  const result = await f.apiFetch('/api/private', { headers: { authorization: 'Bearer explicit' } });
  assert.deepEqual(await result.json(), { explicit: 'Bearer explicit' });
});

test('resilient transport keeps automatic credentials on the configured backend and never persists responses', async t => {
  const f = fixture('resilientNet');
  const previous = global.fetch;
  t.after(() => { global.fetch = previous; f.stopHeartbeat(); });
  const calls = [];
  global.fetch = async (url, init) => { calls.push({ url, init }); throw new Error('offline'); };
  await assert.rejects(f.rget('/api/private', { retries: 0 }), /after 1 attempts across 1 host/);
  assert.equal(calls[0].url, 'https://backend.test/api/private');
  assert.equal(calls[0].init.headers.Authorization, 'Bearer account-a');
  assert.equal(calls[0].init.redirect, 'error');
  assert.equal(calls.length, 1);
  global.fetch = async (_url, init) => response({ account: init.headers.Authorization });
  assert.deepEqual((await f.rget('/api/private')).data, { account: 'Bearer account-a' });
  assert.equal([...f.disk.keys()].filter(key => key.startsWith('rnet:')).length, 0);
  f.switchAccount();
  assert.deepEqual((await f.rget('/api/private')).data, { account: 'Bearer account-b' });
});

test('resilient account change aborts observations, rejects late data and prevents stale cache publication', async t => {
  const f = fixture('resilientNet');
  const previous = global.fetch;
  t.after(() => { global.fetch = previous; f.stopHeartbeat(); });
  const pending = deferred(); let requestSignal;
  global.fetch = async (_url, init) => { requestSignal = init.signal; return pending.promise; };
  const request = f.rget('/api/private', { retries: 0 });
  await tick(); f.switchAccount();
  assert.equal(requestSignal.aborted, true);
  pending.resolve(response({ secret: 'old-account' }));
  await assert.rejects(request, /detached/);
  assert.equal(f.getResilientCacheStats().entries, 0);
});

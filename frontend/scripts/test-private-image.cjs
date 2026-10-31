'use strict';
const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const { compileFunction } = require('node:vm');
const ts = require('typescript');
const ROOT = path.resolve(__dirname, '..');
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a7L8AAAAASUVORK5CYII=', 'base64');
function load(file, imports = {}) {
  const compiled = ts.transpileModule(fs.readFileSync(path.join(ROOT, file), 'utf8'), { fileName: file, reportDiagnostics: true,
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } });
  assert.equal(compiled.diagnostics.length, 0);
  const module = { exports: {} };
  compileFunction(compiled.outputText, ['require', 'module', 'exports'])(id => {
    assert.ok(Object.hasOwn(imports, id), file + ': unexpected import ' + id); return imports[id];
  }, module, module.exports);
  return module.exports;
}
function replace(t, name, value) {
  const old = global[name]; global[name] = value;
  t.after(() => { if (old === undefined) delete global[name]; else global[name] = old; });
}
const tick = () => new Promise(resolve => setImmediate(resolve));
function deferred() { let resolve; const promise = new Promise(yes => { resolve = yes; }); return { promise, resolve }; }
function fixture(base = 'https://backend.test') {
  let epoch = 0, token = 'account-a'; const observers = new Set();
  const owner = { getAuthToken: () => token, getAuthEpoch: () => epoch, initializeStoredToken: async () => {},
    subscribeAuthChanges: fn => { observers.add(fn); return () => observers.delete(fn); } };
  const api = load('src/utils/apiClient.ts', {
    './apiBase': { API_BASE: base }, './requestRecoveryPolicy': load('src/utils/requestRecoveryPolicy.ts'),
    './breadcrumbs': { trail: { add() {} } }, './bootTracer': { traceStep: async () => {} },
    '../foundation/queryCache': { appQueryCache: { clear() {} } }, '../auth/gameforgeAuth': owner,
  });
  return { ...load('src/product/privateImage.ts', { '../utils/apiBase': { API_BASE: base }, '../utils/apiClient': api }),
    change(next = 'account-b') { epoch++; token = next; for (const observer of observers) observer(); } };
}
const pngResponse = () => new Response(PNG, { headers: { 'content-type': 'image/png' } });

test('private raster routes are exact, configured-origin scoped and reject credential queries', () => {
  const f = fixture();
  for (const value of ['/api/playable/game-1/cover.png?v=2', '/api/playable/game-1/cover/opt/2.png', '/api/playable/game-1/card.png',
    '/api/assets/genesis/asset_1.png', '/api/snowball/game-1/scorecard.png', '/api/worldforge/render?scale=region&seed=12&features=cities,roads',
    '/api/worldforge/render.gif?zoom=1.5&q=12-spin', '/api/worldforge/heightmap.png?pan_x=-2&pan_y=0']) {
    assert.equal(f.privateImageUrl(value), 'https://backend.test' + value);
  }
  for (const value of ['https://external.test/api/playable/game/cover.png', 'http://backend.test/api/playable/game/cover.png',
    'https://backend.test:4430/api/playable/game/cover.png', '//external.test/api/playable/game/cover.png',
    '/api/playable/game/raw', '/api/v1/playable/game/cover.png', '/api/playable/game%2fother/cover.png',
    '/api/playable/game/cover.png?token=secret', '/api/playable/game/cover.png?v=1&v=2',
    '/api/worldforge/render?Authorization=secret', '/api/worldforge/render?seed=https://external.test/',
    '/api/playable/game/cover.png#secret', 'https://user@backend.test/api/playable/game/cover.png']) {
    assert.throws(() => f.privateImageUrl(value), /Invalid private image/);
  }
  const prefixed = fixture('https://backend.test/product');
  assert.equal(prefixed.privateImageUrl('https://backend.test/product/api/playable/game/cover.png'), 'https://backend.test/product/api/playable/game/cover.png');
  assert.throws(() => prefixed.privateImageUrl('https://backend.test/api/playable/game/cover.png'), /Invalid private image/);
});

test('real canonical auth headers fetch bytes once and only a raster data URI leaves the loader', async t => {
  const f = fixture(), calls = [];
  replace(t, 'fetch', async (url, init) => { calls.push({ url, init }); return pngResponse(); });
  const result = await f.loadPrivateImage('/api/playable/game/cover.png?v=1');
  assert.equal(result, 'data:image/png;base64,' + PNG.toString('base64'));
  assert.equal(calls.length, 1); assert.equal(calls[0].init.headers.Authorization, 'Bearer account-a');
  assert.equal(calls[0].init.redirect, 'error'); assert.equal(calls[0].init.cache, 'no-store'); assert.equal(calls[0].init.credentials, 'omit');
  assert.equal(calls[0].url.includes('account-a'), false);
});

test('MIME confusion, SVG and byte-small PNG/GIF pixel bombs fail closed', async t => {
  const f = fixture();
  const hugePng = Buffer.from(PNG); hugePng.writeUInt32BE(100000, 16); hugePng.writeUInt32BE(100000, 20);
  const cases = [['image/svg+xml', '<svg></svg>'], ['text/html', '<html>secret</html>'], ['image/png', '<html>secret</html>'],
    ['image/png', hugePng], ['image/gif', Buffer.from([71, 73, 70, 56, 57, 97, 255, 255, 255, 255])]];
  replace(t, 'fetch', async () => new Response(cases[0][1], { headers: { 'content-type': cases[0][0] } }));
  for (const [mime, bytes] of cases) {
    global.fetch = async () => new Response(bytes, { headers: { 'content-type': mime } });
    await assert.rejects(f.loadPrivateImage('/api/playable/game/cover.png'), /format is unsupported|content is invalid/);
  }
});

test('advertised oversized or malformed lengths cancel before any body allocation', async () => {
  const f = fixture();
  for (const length of [String(f.MAX_PRIVATE_IMAGE_BYTES + 1), '-1', 'not-a-number']) {
    let cancelled = 0, read = 0;
    const response = { headers: new Headers({ 'content-length': length }), body: { cancel: async () => { cancelled++; }, getReader() { read++; } } };
    await assert.rejects(f.readPrivateImageBytes(response), /exceeds/);
    assert.equal(cancelled, 1); assert.equal(read, 0);
  }
});

test('streamed byte overflow cancels and native arrayBuffer overflow is rejected', async () => {
  const f = fixture(); let cancelled = false, chunks = 0;
  const response = new Response(new ReadableStream({ pull(controller) { chunks++; controller.enqueue(new Uint8Array(512 * 1024)); }, cancel() { cancelled = true; } }));
  await assert.rejects(f.readPrivateImageBytes(response), /exceeds/);
  assert.equal(cancelled, true); assert.ok(chunks <= 10);
  await assert.rejects(f.readPrivateImageBytes({ headers: new Headers(), arrayBuffer: async () => new ArrayBuffer(f.MAX_PRIVATE_IMAGE_BYTES + 1) }), /exceeds/);
});

test('one-byte streamed chunks preserve exact image bytes and base64 padding', async t => {
  const f = fixture(); let offset = 0;
  replace(t, 'fetch', async () => new Response(new ReadableStream({ pull(controller) {
    if (offset === PNG.length) controller.close(); else controller.enqueue(PNG.subarray(offset, ++offset));
  } }), { headers: { 'content-type': 'image/png' } }));
  assert.equal(await f.loadPrivateImage('/api/playable/game/cover.png'), 'data:image/png;base64,' + PNG.toString('base64'));
});

test('an endless stream of empty chunks exhausts a finite fragmentation bound', async () => {
  const f = fixture(); let cancelled = false;
  const response = new Response(new ReadableStream({ pull(controller) { controller.enqueue(new Uint8Array(0)); }, cancel() { cancelled = true; } }));
  await assert.rejects(f.readPrivateImageBytes(response), /fragmented/); assert.equal(cancelled, true);
});

test('logout settles immediately and fences native body reads that ignore abort', async t => {
  const f = fixture(), body = deferred(), started = deferred(); let requestSignal;
  replace(t, 'fetch', async (_url, init) => { requestSignal = init.signal; return { ok: true, headers: new Headers({ 'content-type': 'image/png' }),
    arrayBuffer() { started.resolve(); return body.promise; } }; });
  const pending = f.loadPrivateImage('/api/playable/game/cover.png');
  await started.promise; f.change('');
  await assert.rejects(pending, /cancelled/); assert.equal(requestSignal.aborted, true);
  body.resolve(PNG.buffer.slice(PNG.byteOffset, PNG.byteOffset + PNG.byteLength)); await tick();
});

test('absolute deadline covers stalled native fetch and network failures never retry', async t => {
  const f = fixture(), pending = deferred(); let calls = 0;
  const setTimer = global.setTimeout;
  replace(t, 'setTimeout', (fn, ms, ...args) => setTimer(fn, ms === f.PRIVATE_IMAGE_TIMEOUT_MS ? 10 : ms, ...args));
  replace(t, 'fetch', async () => { calls++; return pending.promise; });
  await assert.rejects(f.loadPrivateImage('/api/playable/game/cover.png'), /timed out/); assert.equal(calls, 1);
  pending.resolve(pngResponse()); await tick();
  global.fetch = async () => { calls++; throw new Error('Bearer account-a private internal URL'); };
  await assert.rejects(f.loadPrivateImage('/api/playable/game/cover.png'), error => /could not be loaded/.test(error.message) && !/account-a/.test(error.message));
  assert.equal(calls, 2);
});

function componentFixture() {
  let epoch = 0, cursor = 0; const slots = [], effects = [], observers = new Set(), calls = [];
  const React = {
    useState(initial) { const i = cursor++; if (!slots[i]) slots[i] = { value: initial }; return [slots[i].value, value => { slots[i].value = value; }]; },
    useRef(value) { const i = cursor++; if (!slots[i]) slots[i] = { current: value }; return slots[i]; },
    useSyncExternalStore(subscribe, snapshot) { const i = cursor++; if (!slots[i]) slots[i] = { cleanup: subscribe(() => {}) }; return snapshot(); },
    useEffect(run, deps) { const i = cursor++, old = slots[i]; if (!old || deps.some((value, j) => !Object.is(value, old.deps[j]))) {
      const next = { deps, cleanup: old?.cleanup }; slots[i] = next; effects.push(() => { next.cleanup?.(); next.cleanup = run(); });
    } },
  };
  const element = (type, props) => ({ type, props });
  const wire = { load: (uri, signal) => { const wait = deferred(); calls.push({ uri, signal, wait }); return wait.promise; } };
  const auth = { getAuthEpoch: () => epoch, subscribeAuthChanges(fn) { observers.add(fn); return () => observers.delete(fn); } };
  const platform = { OS: 'web' }, clipboard = { setImageAsync: async () => {} };
  const exports = load('src/components/PrivateImage.tsx', {
    react: { __esModule: true, default: React, ...React }, 'react/jsx-runtime': { jsx: element, jsxs: element, Fragment: 'Fragment' },
    'react-native': { Image: 'Image', View: 'View', Platform: platform }, 'expo-clipboard': clipboard,
    '../auth/gameforgeAuth': auth, '../product/privateImage': { loadPrivateImage: (...args) => wire.load(...args) },
  });
  return { ...exports, calls, wire, platform, clipboard,
    render(uri = '/api/playable/game/cover.png', props = {}) { cursor = 0; return exports.default({ uri, ...props }); },
    effects() { while (effects.length) effects.shift()(); }, change() { epoch++; for (const fn of observers) fn(); },
    unmount() { for (const slot of slots) slot?.cleanup?.(); },
  };
}

test('component clears painted bytes on account/URL change before effects and fences old native completions', async () => {
  const f = componentFixture(); f.render(); f.effects();
  f.calls[0].wait.resolve('data:image/png;base64,account-a'); await tick();
  assert.equal(f.render().props.source.uri, 'data:image/png;base64,account-a');
  f.change(); assert.equal(f.render().type, 'View'); f.effects();
  assert.equal(f.calls[0].signal.aborted, true);
  f.calls[1].wait.resolve('data:image/png;base64,account-b'); await tick();
  assert.equal(f.render().props.source.uri, 'data:image/png;base64,account-b');
  assert.equal(f.render('/api/playable/other/cover.png').type, 'View'); f.effects();
  const last = f.calls.at(-1); f.unmount(); last.wait.resolve('data:image/png;base64,unmounted'); await tick();
  assert.equal(last.signal.aborted, true);
});

test('component preserves the existing fallback/onError contract and export uses bounded data bytes', async t => {
  const f = componentFixture(); let errors = 0, starts = 0, ends = 0;
  const callbacks = { fallback: 'cover glyph', onError: () => { errors++; }, onLoadStart: () => { starts++; }, onLoadEnd: () => { ends++; } };
  f.render(undefined, callbacks); f.effects();
  // A failed authenticated read reports the normal image error contract.
  f.wire.load = async () => { throw new Error('unavailable'); };
  f.change(); f.render(undefined, callbacks); f.effects(); await tick();
  assert.equal(errors, 1); assert.equal(starts, 2); assert.equal(ends, 1);
  assert.equal(f.render(undefined, { fallback: 'cover glyph' }).props.children, 'cover glyph');
  const links = [];
  replace(t, 'document', { createElement() { const link = { click() { links.push({ href: this.href, download: this.download }); }, remove() {} }; return link; }, body: { appendChild() {} } });
  f.wire.load = async () => 'data:image/png;base64,' + PNG.toString('base64');
  assert.equal(await f.savePrivateImage('/api/playable/game/card.png', 'unsafe/name.png'), 'saved');
  assert.equal(links[0].download, 'unsafe_name.png'); assert.ok(links[0].href.startsWith('data:image/png;base64,'));
  f.unmount();
});

test('an account change between bounded bytes and export continuation prevents a stale download', async t => {
  const f = componentFixture(), data = deferred(); let downloads = 0;
  replace(t, 'document', { createElement() { return { click() { downloads++; }, remove() {} }; }, body: { appendChild() {} } });
  f.wire.load = () => data.promise;
  const saving = f.savePrivateImage('/api/playable/game/card.png');
  data.resolve('data:image/png;base64,' + PNG.toString('base64')); f.change();
  await assert.rejects(saving, /account changed/); assert.equal(downloads, 0); f.unmount();
});

test('native export copies only bounded image bytes and rejects an acknowledgement after account change', async () => {
  const f = componentFixture(), writing = deferred(), written = deferred(); let content;
  f.platform.OS = 'native';
  f.wire.load = async () => 'data:image/png;base64,' + PNG.toString('base64');
  f.clipboard.setImageAsync = value => { content = value; writing.resolve(); return written.promise; };
  const saving = f.savePrivateImage('/api/playable/game/card.png'); await writing.promise;
  f.change(); written.resolve(); await assert.rejects(saving, /account changed/);
  assert.equal(content, PNG.toString('base64')); f.unmount();
});

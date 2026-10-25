'use strict';
const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const { compileFunction } = require('node:vm');
const ts = require('typescript');
const ROOT = path.resolve(__dirname, '..');
const SOURCE = path.join(ROOT, 'src/product/privateAtlasExport.ts');
const ORIGINAL = '<!doctype html><meta charset="utf-8"><title>Private 🐉 atlas</title><script>window.parent.__atlasExecuted=true;window.parent.localStorage.getItem("atlasParentToken");fetch("/exfil");</script><h1>Original atlas bytes</h1>';
const tick = () => new Promise(resolve => setImmediate(resolve));
function deferred() { let resolve; const promise = new Promise(yes => { resolve = yes; }); return { promise, resolve }; }
function compiled() {
  const result = ts.transpileModule(fs.readFileSync(SOURCE, 'utf8'), {
    fileName: SOURCE, reportDiagnostics: true,
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true },
  });
  assert.equal(result.diagnostics.length, 0); return result.outputText;
}
function fixture(platform = 'web') {
  let epoch = 0;
  const observers = new Set(), requests = [], writes = [], shares = [], deletions = [];
  const wire = { get: async () => ({ ok: true, data: ORIGINAL }), write: async () => {}, available: async () => true, share: async () => {} };
  const fileSystem = { cacheDirectory: 'file:///private-cache/', EncodingType: { UTF8: 'utf8' },
    writeAsStringAsync: async (file, text, options) => { writes.push({ file, text, options }); return wire.write(file, text, options); },
    deleteAsync: async (file, options) => { deletions.push({ file, options }); } };
  const imports = {
    'react-native': { Platform: { OS: platform } }, 'expo-file-system/legacy': fileSystem,
    'expo-sharing': { isAvailableAsync: () => wire.available(), shareAsync: async (file, options) => { shares.push({ file, options }); return wire.share(file, options); } },
    '../utils/apiClient': { __esModule: true, default: { get: async (url, options) => { requests.push({ url, options }); return wire.get(url, options); } } },
    '../auth/gameforgeAuth': { getAuthEpoch: () => epoch, subscribeAuthChanges(fn) { observers.add(fn); return () => observers.delete(fn); } },
  };
  const module = { exports: {} };
  compileFunction(compiled(), ['require', 'module', 'exports'])(id => {
    assert.ok(Object.hasOwn(imports, id), 'unexpected atlas dependency ' + id); return imports[id];
  }, module, module.exports);
  return { ...module.exports, wire, requests, writes, shares, deletions, fileSystem, observers,
    changeAccount() { epoch++; for (const fn of observers) fn(); } };
}
function webFixture(t) {
  const urls = new Map(), blobs = [], links = [], revoked = [];
  const previousURL = global.URL, previousDocument = global.document;
  global.URL = { createObjectURL(blob) { const url = 'blob:atlas-' + blobs.length; blobs.push(blob); urls.set(url, blob); return url; },
    revokeObjectURL(url) { revoked.push(url); urls.delete(url); } };
  const wire = { click() {} };
  global.document = { createElement(tag) { assert.equal(tag, 'a'); const link = { href: '', download: '', removed: false,
    remove() { this.removed = true; }, click() { wire.click(this); } }; links.push(link); return link; },
    body: { appendChild(link) { assert.ok(links.includes(link)); } } };
  t.after(() => { global.URL = previousURL; if (previousDocument === undefined) delete global.document; else global.document = previousDocument; });
  return { urls, blobs, links, revoked, wire };
}

test('atlas export rejects invalid runtime IDs and traversal before canonical API I/O', async () => {
  const f = fixture('ios');
  for (const id of [undefined, null, 42, {}, [], '', '../private', 'a/b', 'a%2fb', 'game?token=private', 'a'.repeat(129), ' game ']) await assert.rejects(f.downloadPrivateAtlas(id));
  assert.equal(f.requests.length, 0); assert.equal(f.observers.size, 0);
});

test('web atlas export preserves the original HTML as an explicit octet-stream download', async t => {
  const f = fixture(), web = webFixture(t);
  await f.downloadPrivateAtlas('game_1-abc');
  assert.equal(f.MAX_ATLAS_EXPORT_BYTES, 2 * 1024 * 1024);
  assert.equal(f.requests.length, 1); assert.equal(f.requests[0].url, '/api/snowball/game_1-abc/atlas.html');
  const options = f.requests[0].options;
  assert.equal(options.responseType, 'text'); assert.equal(options.headers.Accept, 'text/html');
  assert.equal(options.maxResponseChars, f.MAX_ATLAS_EXPORT_BYTES); assert.equal(options.timeoutMs, 15000); assert.equal(options.retries, 0);
  assert.equal(web.blobs.length, 1); assert.equal(web.blobs[0].type, 'application/octet-stream');
  assert.equal(await web.blobs[0].text(), ORIGINAL); assert.equal(web.links[0].download, 'game_1-abc-world-atlas.html');
  assert.ok(web.links[0].href.startsWith('blob:')); assert.equal(web.links[0].removed, true);
  assert.equal(web.revoked.length, 1); assert.equal(web.urls.size, 0); assert.equal(f.observers.size, 0);
});

test('failed, non-text, empty and UTF-8 oversized atlas responses create no browser artifact', async t => {
  const f = fixture(), web = webFixture(t);
  for (const result of [{ ok: false, error: 'secret internal detail' }, { ok: true, data: {} }, { ok: true, data: ' \n' },
    { ok: true, data: '🐉'.repeat(f.MAX_ATLAS_EXPORT_BYTES / 4 + 1) }]) {
    f.wire.get = async () => result; await assert.rejects(f.downloadPrivateAtlas('game'), error => !error.message.includes('secret internal'));
  }
  assert.equal(web.blobs.length, 0); assert.equal(web.links.length, 0); assert.equal(f.observers.size, 0);
});

test('abort and account changes fence native-ignore fetch completions before any file or URL exists', async t => {
  const web = webFixture(t);
  for (const action of ['abort', 'account']) {
    const f = fixture(), response = deferred(), controller = new AbortController();
    f.wire.get = () => response.promise; const pending = f.downloadPrivateAtlas('game', controller.signal);
    if (action === 'abort') controller.abort(); else f.changeAccount();
    assert.equal(f.requests[0].options.signal.aborted, true);
    response.resolve({ ok: true, data: ORIGINAL }); await assert.rejects(pending, /cancel/i);
    assert.equal(f.observers.size, 0);
  }
  const f = fixture(), controller = new AbortController(); controller.abort();
  await assert.rejects(f.downloadPrivateAtlas('game', controller.signal), /cancel/i); assert.equal(f.requests.length, 0);
  assert.equal(web.blobs.length, 0);
});

test('logout after browser dispatch removes the anchor and revokes its object URL', async t => {
  const f = fixture(), web = webFixture(t); web.wire.click = () => f.changeAccount();
  await assert.rejects(f.downloadPrivateAtlas('game'), /cancel/i);
  assert.equal(web.revoked.length, 1); assert.equal(web.urls.size, 0); assert.equal(web.links[0].removed, true);
  assert.equal(f.observers.size, 0);
});

test('native export writes exact HTML to a bounded temporary file and shares only a download MIME', async () => {
  const f = fixture('ios'); await f.downloadPrivateAtlas('native_game');
  assert.equal(f.writes.length, 1); assert.ok(f.writes[0].file.startsWith('file:///private-cache/'));
  assert.ok(f.writes[0].file.endsWith('-native_game-world-atlas.html'));
  assert.equal(f.writes[0].text, ORIGINAL); assert.equal(f.writes[0].options.encoding, 'utf8');
  assert.equal(f.shares.length, 1); assert.equal(f.shares[0].file, f.writes[0].file);
  assert.equal(f.shares[0].options.mimeType, 'application/octet-stream');
  assert.ok(f.deletions.some(value => value.file === f.writes[0].file && value.options.idempotent === true));
  assert.equal(f.observers.size, 0);
});

test('unsupported native sharing fails visibly and never writes a temporary HTML file', async () => {
  for (const unsupported of ['cache', 'sharing']) {
    const f = fixture('android');
    if (unsupported === 'cache') f.fileSystem.cacheDirectory = null; else f.wire.available = async () => false;
    await assert.rejects(f.downloadPrivateAtlas('game'), /unavailable/i);
    assert.equal(f.writes.length, 0); assert.equal(f.shares.length, 0); assert.equal(f.observers.size, 0);
  }
});

test('a native write ignoring logout is erased before and after completion and never shared', async () => {
  const f = fixture('ios'), write = deferred(); f.wire.write = () => write.promise;
  const pending = f.downloadPrivateAtlas('game'); await tick(); assert.equal(f.writes.length, 1);
  f.changeAccount(); assert.equal(f.requests[0].options.signal.aborted, true); assert.equal(f.deletions.length, 1);
  write.resolve(); await assert.rejects(pending, /cancel/i);
  assert.ok(f.deletions.length >= 2); assert.equal(f.shares.length, 0); assert.equal(f.observers.size, 0);
});

test('native availability and share failures retain cleanup and account fences', async () => {
  const f = fixture('ios'), available = deferred(); f.wire.available = () => available.promise;
  const pending = f.downloadPrivateAtlas('game'); await tick(); f.changeAccount(); available.resolve(true);
  await assert.rejects(pending, /cancel/i); assert.equal(f.writes.length, 0); assert.equal(f.observers.size, 0);
  const failure = fixture('android'); failure.wire.share = async () => { throw new Error('share adapter unavailable'); };
  await assert.rejects(failure.downloadPrivateAtlas('game'), /share adapter/);
  assert.equal(failure.writes.length, 1); assert.ok(failure.deletions.some(value => value.file === failure.writes[0].file));
  assert.equal(failure.observers.size, 0);
});

const PLAYWRIGHT = '/opt/codex/runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright';
const browserAvailable = fs.existsSync('/usr/bin/chromium') && fs.existsSync(PLAYWRIGHT);
test('real Chromium downloads exact atlas bytes without rendering HTML or reading parent storage', { skip: browserAvailable ? false : 'existing Chromium/Playwright runtime is unavailable' }, async t => {
  const { chromium } = require(PLAYWRIGHT); let exfil = 0;
  const server = http.createServer((req, res) => {
    if (req.url.startsWith('/exfil')) exfil++;
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end('<!doctype html><title>Atlas download canary</title><button id="export">Download controlled atlas</button>');
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(() => new Promise(resolve => server.close(resolve)));
  const browser = await chromium.launch({ executablePath: '/usr/bin/chromium', headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  t.after(() => browser.close());
  const page = await browser.newPage({ acceptDownloads: true }), errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const address = 'http://127.0.0.1:' + server.address().port;
  await page.route('**/*', route => new URL(route.request().url()).origin === address ? route.continue() : route.abort());
  await page.goto(address, { waitUntil: 'domcontentloaded' });
  await page.evaluate(({ code, original }) => {
    window.__atlasExecuted = false; window.__tokenReads = 0;
    localStorage.setItem('atlasParentToken', 'local-canary-secret');
    const getItem = Storage.prototype.getItem;
    Storage.prototype.getItem = function (key) { if (key === 'atlasParentToken') window.__tokenReads++; return getItem.call(this, key); };
    const observations = window.__atlasObservations = { requests: [], urls: [], revoked: [] };
    const create = URL.createObjectURL.bind(URL), revoke = URL.revokeObjectURL.bind(URL);
    URL.createObjectURL = blob => { const url = create(blob); observations.urls.push({ url, type: blob.type, size: blob.size }); return url; };
    URL.revokeObjectURL = url => { observations.revoked.push(url); revoke(url); };
    const imports = {
      'react-native': { Platform: { OS: 'web' } }, 'expo-file-system/legacy': {}, 'expo-sharing': {},
      '../utils/apiClient': { __esModule: true, default: { get: async (url, options) => { observations.requests.push({ url, responseType: options.responseType, retries: options.retries }); return { ok: true, data: original }; } } },
      '../auth/gameforgeAuth': { getAuthEpoch: () => 0, subscribeAuthChanges: () => () => {} },
    };
    const module = { exports: {} };
    new Function('require', 'module', 'exports', code)(id => { if (!(id in imports)) throw new Error('Unexpected canary import'); return imports[id]; }, module, module.exports);
    document.querySelector('#export').onclick = () => { window.__atlasPromise = module.exports.downloadPrivateAtlas('browser_game'); };
  }, { code: compiled(), original: ORIGINAL });
  const downloaded = page.waitForEvent('download'); await page.click('#export'); const download = await downloaded;
  assert.equal(download.suggestedFilename(), 'browser_game-world-atlas.html');
  assert.equal(fs.readFileSync(await download.path(), 'utf8'), ORIGINAL);
  await page.evaluate(() => window.__atlasPromise);
  const observed = await page.evaluate(() => ({ executed: window.__atlasExecuted, tokenReads: window.__tokenReads,
    frames: window.frames.length, links: document.querySelectorAll('a').length, ...window.__atlasObservations }));
  assert.equal(observed.executed, false); assert.equal(observed.tokenReads, 0); assert.equal(observed.frames, 0); assert.equal(observed.links, 0);
  assert.equal(observed.urls.length, 1); assert.equal(observed.urls[0].type, 'application/octet-stream');
  assert.deepEqual(observed.revoked, [observed.urls[0].url]); assert.equal(observed.requests[0].url, '/api/snowball/browser_game/atlas.html');
  assert.equal(observed.requests[0].responseType, 'text'); assert.equal(observed.requests[0].retries, 0);
  assert.equal(page.url(), address + '/'); assert.equal(exfil, 0); assert.deepEqual(errors, []);
});

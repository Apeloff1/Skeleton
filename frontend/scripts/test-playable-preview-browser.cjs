'use strict';
// Controlled localhost canary: real auth transport + real Chromium's opaque
// srcdoc sandbox. This does not build the app or call an installed deployment.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const { test } = require('node:test');
const { compileFunction } = require('node:vm');
const ts = require('typescript');

const ROOT = path.resolve(__dirname, '..');
const FIXTURE_TOKEN = 'playable-browser-canary-account';
function source(relative) { return fs.readFileSync(path.join(ROOT, relative), 'utf8'); }
function compile(relative) {
  const output = ts.transpileModule(source(relative), { fileName: relative, reportDiagnostics: true,
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true } });
  assert.equal(output.diagnostics.length, 0, relative + ' must compile');
  return output.outputText;
}
function load(relative, imports = {}) {
  const module = { exports: {} };
  compileFunction(compile(relative), ['require', 'module', 'exports'])(id => {
    assert.ok(Object.hasOwn(imports, id), relative + ': unexpected dependency ' + id);
    return imports[id];
  }, module, module.exports);
  return module.exports;
}
function browserRuntime() {
  for (const modulePath of ['playwright', '/opt/codex/runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright']) {
    try {
      const { chromium } = require(modulePath);
      const executablePath = [process.env.CHROMIUM_EXECUTABLE_PATH, '/usr/bin/chromium', chromium.executablePath()]
        .find(value => value && fs.existsSync(value));
      if (executablePath) return { chromium, executablePath };
    } catch { /* Another declared local browser installation may be present. */ }
  }
  return null;
}
const runtime = browserRuntime();

function browserHelper(base) {
  return `(function () {
    const module = { exports: {} }, exports = module.exports;
    const require = id => {
      if (id === '../utils/apiClient') return { __esModule: true, default: { get() { throw new Error('Browser canary loads documents through the verified Node transport.'); } } };
      if (id === '../utils/apiBase') return { API_BASE: ${JSON.stringify(base)} };
      if (id === '../auth/gameforgeAuth') return { getAuthEpoch: () => 0 };
      throw new Error('Unexpected helper dependency: ' + id);
    };
    ${compile('src/product/playablePreview.ts')}
    globalThis.__playablePreview = module.exports;
  })();`;
}

test('authenticated playable HTML runs inside an opaque sandbox without parent credentials or network authority', {
  skip: runtime ? false : 'Requires a local Playwright installation and Chromium executable', timeout: 30_000,
}, async t => {
  const requests = [];
  let gameHtml = '';
  const server = http.createServer((request, response) => {
    const pathname = new URL(request.url, 'http://localhost').pathname;
    const authorized = request.headers.authorization === 'Bearer ' + FIXTURE_TOKEN;
    requests.push({ pathname, method: request.method, authorized, destination: request.headers['sec-fetch-dest'] || null });
    if (pathname === '/api/playable/canary-game/raw') {
      response.writeHead(authorized ? 200 : 401, { 'Content-Type': authorized ? 'text/html; charset=utf-8' : 'application/json', 'Cache-Control': 'no-store' });
      response.end(authorized ? gameHtml : '{"detail":"Authentication required"}');
      return;
    }
    if (pathname === '/application') {
      response.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      response.end('<!doctype html><html><head><title>Playable preview canary</title></head><body><h1 id="application-marker">Trusted application</h1></body></html>');
      return;
    }
    response.writeHead(204); response.end();
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(() => new Promise(resolve => { server.closeAllConnections?.(); server.close(resolve); }));
  const base = 'http://127.0.0.1:' + server.address().port;
  const rawUri = base + '/api/playable/canary-game/raw';
  gameHtml = `<!doctype html><html><head><title>Generated game</title></head><body>
    <p id="game-status">Game booting</p><script>
    (async function () {
      const probe = { scriptRan: true, localStorage: false, sessionStorage: false,
        parentStorageDenied: false, parentDomDenied: false, fetchBlocked: false, quotaBounded: false };
      try { localStorage.setItem('game-save', 'local-progress'); probe.localStorage = localStorage.getItem('game-save') === 'local-progress'; } catch (_) {}
      try { sessionStorage.setItem('game-save', 'session-progress'); probe.sessionStorage = sessionStorage.getItem('game-save') === 'session-progress'; } catch (_) {}
      probe.ownTokenAbsent = localStorage.getItem('gameforge_auth_token') === null;
      try { localStorage.setItem('oversized-save', 'x'.repeat(16385)); } catch (error) { probe.quotaBounded = error.name === 'QuotaExceededError'; }
      try { probe.parentToken = parent.localStorage.getItem('gameforge_auth_token'); } catch (_) { probe.parentStorageDenied = true; }
      try { parent.document.getElementById('application-marker').textContent = 'untrusted overwrite'; } catch (_) { probe.parentDomDenied = true; }
      try { await fetch(${JSON.stringify(base + '/blocked-fetch')}); } catch (_) { probe.fetchBlocked = true; }
      const image = new Image(); image.src = ${JSON.stringify(base + '/blocked-image')}; document.body.appendChild(image);
      const form = document.createElement('form'); form.method = 'POST'; form.action = ${JSON.stringify(base + '/blocked-form')}; form.target = '_top'; document.body.appendChild(form); try { form.submit(); } catch (_) {}
      const link = document.createElement('a'); link.href = ${JSON.stringify(base + '/blocked-navigation')}; link.target = '_top'; document.body.appendChild(link); try { link.click(); } catch (_) {}
      document.getElementById('game-status').textContent = 'Game running with local saves';
      parent.postMessage({ fixtureProbe: probe }, '*');
      parent.postMessage({ __pl_error: true, message: 'Actual generated game error' }, '*');
    })();
    </script></body></html>`;

  // The protected endpoint denies a raw navigation without canonical auth.
  assert.equal((await fetch(rawUri)).status, 401);
  let token = '', initializations = 0;
  const observers = new Set();
  const authOwner = { getAuthToken: () => token, getAuthEpoch: () => 0,
    initializeStoredToken: async () => { initializations++; token = FIXTURE_TOKEN; },
    subscribeAuthChanges: observer => { observers.add(observer); return () => observers.delete(observer); } };
  const api = load('src/utils/apiClient.ts', {
    './apiBase': { API_BASE: base }, './requestRecoveryPolicy': load('src/utils/requestRecoveryPolicy.ts'),
    './breadcrumbs': { trail: { add() {} } }, './bootTracer': { traceStep: async () => {} },
    '../foundation/queryCache': { appQueryCache: { clear() {} } }, '../auth/gameforgeAuth': authOwner,
  });
  const preview = load('src/product/playablePreview.ts', {
    '../utils/apiClient': { __esModule: true, default: api.default },
    '../utils/apiBase': { API_BASE: base }, '../auth/gameforgeAuth': authOwner,
  });
  const prepared = await preview.loadPlayableDocument(rawUri);
  assert.equal(typeof prepared, 'string'); assert.ok(prepared.includes('Game booting'));
  assert.ok(initializations > 0, 'The canonical transport must hydrate the existing auth owner');
  assert.equal(requests.filter(request => request.pathname.endsWith('/raw') && request.authorized).length, 1);
  assert.equal(preview.PLAYABLE_FRAME_SANDBOX, 'allow-scripts allow-pointer-lock');
  assert.equal(preview.PLAYABLE_FRAME_ALLOW, 'autoplay; fullscreen; gamepad');

  const browser = await runtime.chromium.launch({ executablePath: runtime.executablePath, headless: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  t.after(() => browser.close());
  const page = await browser.newPage();
  const browserRawRequests = [];
  page.on('request', request => { if (new URL(request.url()).pathname.endsWith('/raw')) browserRawRequests.push(request.url()); });
  await page.goto(base + '/application');
  await page.evaluate(() => localStorage.setItem('gameforge_auth_token', 'parent-only-canary-token'));
  await page.addScriptTag({ content: browserHelper(base) });
  await page.evaluate(({ prepared }) => {
    globalThis.__fixtureMessages = []; globalThis.__fixtureProbes = []; globalThis.__foreignProbes = [];
    window.addEventListener('message', event => {
      const frame = document.getElementById('game-frame');
      const accepted = globalThis.__playablePreview.playableMessage(event, frame?.contentWindow);
      if (accepted !== null) globalThis.__fixtureMessages.push(accepted);
      if (event.data?.fixtureProbe) globalThis.__fixtureProbes.push({ origin: event.origin,
        sourceMatches: event.source === frame?.contentWindow, probe: event.data.fixtureProbe });
      if (event.data?.fixtureForeignProbe) globalThis.__foreignProbes.push({ origin: event.origin,
        sourceMatches: event.source === frame?.contentWindow, emptyStorage: event.data.fixtureForeignProbe.emptyStorage });
    });
    const frame = document.createElement('iframe'); frame.id = 'game-frame';
    frame.setAttribute('sandbox', globalThis.__playablePreview.PLAYABLE_FRAME_SANDBOX);
    frame.setAttribute('allow', globalThis.__playablePreview.PLAYABLE_FRAME_ALLOW);
    frame.srcdoc = prepared; document.body.appendChild(frame);
  }, { prepared });
  await page.waitForFunction(() => globalThis.__fixtureProbes.length > 0 && globalThis.__fixtureMessages.length > 0);
  const result = await page.evaluate(() => ({ probe: globalThis.__fixtureProbes[0],
    messages: globalThis.__fixtureMessages, parentMarker: document.getElementById('application-marker').textContent,
    parentToken: localStorage.getItem('gameforge_auth_token'), rawSource: document.getElementById('game-frame').getAttribute('src') }));
  assert.equal(result.probe.origin, 'null'); assert.equal(result.probe.sourceMatches, true);
  assert.equal(result.probe.probe.scriptRan, true);
  assert.equal(result.probe.probe.localStorage, true); assert.equal(result.probe.probe.sessionStorage, true);
  assert.equal(result.probe.probe.ownTokenAbsent, true); assert.equal(result.probe.probe.quotaBounded, true);
  assert.equal(result.probe.probe.parentStorageDenied, true); assert.equal(result.probe.probe.parentDomDenied, true);
  assert.equal(result.probe.probe.fetchBlocked, true); assert.equal(result.probe.probe.parentToken, undefined);
  assert.equal(result.parentMarker, 'Trusted application'); assert.equal(result.parentToken, 'parent-only-canary-token');
  assert.equal(result.rawSource, null); assert.deepEqual(result.messages, ['Actual generated game error']);
  assert.equal(page.url(), base + '/application');
  await page.locator('#game-frame').contentFrame().locator('#game-status').waitFor({ state: 'visible' });
  assert.equal(await page.locator('#game-frame').contentFrame().locator('#game-status').innerText(), 'Game running with local saves');

  // An actual second opaque frame must not impersonate this preview's errors.
  await page.evaluate(() => {
    const foreign = document.createElement('iframe'); foreign.id = 'foreign-frame';
    foreign.setAttribute('sandbox', globalThis.__playablePreview.PLAYABLE_FRAME_SANDBOX);
    foreign.srcdoc = globalThis.__playablePreview.preparePlayableDocument('<script>parent.postMessage({__pl_error:true,message:"Foreign frame error"},"*");parent.postMessage({fixtureForeignProbe:{emptyStorage:localStorage.getItem("game-save")===null}},"*");<\/script>');
    document.body.appendChild(foreign);
    window.postMessage({ __pl_error: true, message: 'Application-origin spoof' }, '*');
  });
  await page.waitForFunction(() => globalThis.__foreignProbes.length > 0);
  await page.waitForTimeout(300);
  const filtering = await page.evaluate(() => {
    const frame = document.getElementById('game-frame').contentWindow;
    const guard = globalThis.__playablePreview.playableMessage;
    return { messages: globalThis.__fixtureMessages, foreign: globalThis.__foreignProbes[0],
      wrongOrigin: guard({ source: frame, origin: location.origin, data: { __pl_error: true, message: 'bad origin' } }, frame),
      wrongShape: guard({ source: frame, origin: 'null', data: { __pl_error: true, message: { token: 'bad shape' } } }, frame),
      oversized: guard({ source: frame, origin: 'null', data: { __pl_error: true, message: 'x'.repeat(100000) } }, frame) };
  });
  assert.deepEqual(filtering.messages, ['Actual generated game error']);
  assert.deepEqual(filtering.foreign, { origin: 'null', sourceMatches: false, emptyStorage: true });
  assert.equal(filtering.wrongOrigin, null); assert.equal(filtering.wrongShape, null);
  assert.equal(filtering.oversized, null);
  assert.deepEqual(browserRawRequests, [], 'An iframe must never navigate to the protected raw endpoint');
  assert.deepEqual(requests.filter(request => request.pathname.startsWith('/blocked-')), [], 'Game egress, forms and top navigation must remain blocked');
});

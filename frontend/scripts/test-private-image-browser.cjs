'use strict';
// Local controlled server and real Chromium. No deployment or model is called.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const { test } = require('node:test');
const ts = require('typescript');
const ROOT = path.resolve(__dirname, '..');
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a7L8AAAAASUVORK5CYII=', 'base64');
function runtime() {
  for (const name of ['playwright', '/opt/codex/runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright']) {
    try {
      const { chromium } = require(name);
      const executablePath = [process.env.CHROMIUM_EXECUTABLE_PATH, '/usr/bin/chromium', chromium.executablePath()].find(value => value && fs.existsSync(value));
      if (executablePath) return { chromium, executablePath };
    } catch {}
  }
  return null;
}
const browserRuntime = runtime();
function compile(file) {
  const result = ts.transpileModule(fs.readFileSync(path.join(ROOT, file), 'utf8'), { fileName: file, reportDiagnostics: true,
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true } });
  assert.equal(result.diagnostics.length, 0); return result.outputText;
}
function bootstrap(base) {
  const policy = compile('src/utils/requestRecoveryPolicy.ts'), api = compile('src/utils/apiClient.ts'), image = compile('src/product/privateImage.ts');
  return `(function () {
    let token = '', epoch = 0; const observers = new Set();
    const auth = { getAuthToken: () => token, getAuthEpoch: () => epoch, initializeStoredToken: async () => { token = 'private-image-canary-token'; },
      subscribeAuthChanges: fn => { observers.add(fn); return () => observers.delete(fn); } };
    function run(source, imports) { const module = { exports: {} }; new Function('require', 'module', 'exports', source)(id => {
      if (!Object.hasOwn(imports, id)) throw new Error('Unexpected browser fixture dependency: ' + id); return imports[id];
    }, module, module.exports); return module.exports; }
    const policy = run(${JSON.stringify(policy)}, {});
    const api = run(${JSON.stringify(api)}, { './apiBase': { API_BASE: ${JSON.stringify(base)} }, './requestRecoveryPolicy': policy,
      './breadcrumbs': { trail: { add() {} } }, './bootTracer': { traceStep: async () => {} },
      '../foundation/queryCache': { appQueryCache: { clear() {} } }, '../auth/gameforgeAuth': auth });
    globalThis.__privateImage = run(${JSON.stringify(image)}, { '../utils/apiBase': { API_BASE: ${JSON.stringify(base)} }, '../utils/apiClient': api });
  })();`;
}

test('real browser paints an authenticated bounded data image while direct image navigation is unauthorized', {
  skip: browserRuntime ? false : 'Requires local Playwright and Chromium', timeout: 30_000,
}, async t => {
  const requests = [];
  const server = http.createServer((request, response) => {
    const url = new URL(request.url, 'http://localhost');
    if (url.pathname.startsWith('/api/')) {
      const authorized = request.headers.authorization === 'Bearer private-image-canary-token';
      requests.push({ path: url.pathname, query: url.search, authorized, destination: request.headers['sec-fetch-dest'] || '' });
      if (!authorized) { response.writeHead(401); response.end(); return; }
      if (url.searchParams.get('v') === 'redirect') { response.writeHead(302, { Location: '/api/playable/redirect-target/cover.png' }); response.end(); return; }
      response.writeHead(200, { 'Content-Type': 'image/png', 'Cache-Control': 'private, no-store' }); response.end(PNG); return;
    }
    response.writeHead(200, { 'Content-Type': 'text/html' }); response.end('<!doctype html><html><body><h1>Private image canary</h1></body></html>');
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(() => new Promise(resolve => { server.closeAllConnections?.(); server.close(resolve); }));
  const base = 'http://127.0.0.1:' + server.address().port;
  const browser = await browserRuntime.chromium.launch({ executablePath: browserRuntime.executablePath, headless: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  t.after(() => browser.close());
  const page = await browser.newPage(); await page.goto(base); await page.addScriptTag({ content: bootstrap(base) });
  const observed = await page.evaluate(async () => {
    const legacyDenied = await new Promise(resolve => { const legacy = document.createElement('img');
      legacy.onload = () => { legacy.remove(); resolve(false); }; legacy.onerror = () => { legacy.remove(); resolve(true); };
      legacy.src = '/api/playable/canary/cover.png?v=legacy'; document.body.appendChild(legacy); });
    const data = await globalThis.__privateImage.loadPrivateImage('/api/playable/canary/cover.png');
    const image = document.createElement('img'); image.id = 'authenticated-cover'; image.src = data; document.body.appendChild(image);
    await image.decode();
    let redirectDenied = false;
    try { await globalThis.__privateImage.loadPrivateImage('/api/playable/canary/cover.png?v=redirect'); } catch { redirectDenied = true; }
    return { legacyDenied, redirectDenied, source: image.src, width: image.naturalWidth, height: image.naturalHeight };
  });
  assert.equal(observed.legacyDenied, true); assert.equal(observed.redirectDenied, true);
  assert.equal(observed.width, 1); assert.equal(observed.height, 1);
  assert.equal(observed.source, 'data:image/png;base64,' + PNG.toString('base64'));
  assert.equal(requests.filter(request => request.authorized && request.query === '').length, 1);
  assert.equal(requests.filter(request => request.authorized && request.query === '')[0].destination, 'empty');
  assert.equal(requests.some(request => request.path.includes('redirect-target')), false);
  assert.equal(requests.some(request => request.query.includes('canary-token')), false);
});

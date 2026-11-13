'use strict';
// Exercise the actual preview document builder and Chromium's opaque sandbox.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const { test } = require('node:test');
const { compileFunction } = require('node:vm');
const { spawnSync } = require('node:child_process');
const ts = require('typescript');
const source = fs.readFileSync(path.resolve(__dirname, '../src/features/Jeeves/successorPreviewDocument.ts'), 'utf8');
const compiled = ts.transpileModule(source, { reportDiagnostics: true, compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } });
assert.equal(compiled.diagnostics.length, 0);
const moduleUnderTest = { exports: {} };
compileFunction(compiled.outputText, ['require', 'module', 'exports'])(() => { throw new Error('Unexpected runtime dependency'); }, moduleUnderTest, moduleUnderTest.exports);
const { successorPreviewDocument } = moduleUnderTest.exports;
const file = (path, content) => ({ path, content });

function browserRuntime() {
  for (const name of ['playwright', '/opt/codex/runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright']) {
    try {
      const { chromium } = require(name);
      const executablePath = [process.env.CHROMIUM_EXECUTABLE_PATH, '/usr/bin/chromium', chromium.executablePath()].find(value => value && fs.existsSync(value));
      if (executablePath) return { chromium, executablePath };
    } catch {}
  }
  return null;
}
const runtime = browserRuntime();

test('preview protects all untrusted markup and keeps script source bounded', () => {
  const html = successorPreviewDocument([
    file('game/successor/index.html', '<!-- <head> --><script src="./game.js"></script><head></head>'),
    file('game/successor/game.js', 'window.gameStarted = true;'),
  ]);
  assert.ok(html.indexOf('Content-Security-Policy') < html.indexOf('<!-- <head> -->'));
  assert.match(html, /<script>window\.gameStarted = true;<\/script>/);
  assert.equal(successorPreviewDocument([]), null);
  assert.equal(successorPreviewDocument([file('game/successor/index.html', 'x'.repeat(2 * 1024 * 1024 + 1))]), null);
  const unsafeScript = successorPreviewDocument([file('game/successor/index.html', '<script src="../secret.js"></script>')]);
  assert.ok(!unsafeScript.includes('../secret.js'));
});

test('CSP precedes attacker-controlled tags even with a fake head and blocks their requests', {
  skip: runtime ? false : 'Requires a local Playwright installation and Chromium executable', timeout: 30000,
}, async t => {
  const requests = [];
  const server = http.createServer((request, response) => {
    requests.push(request.url);
    response.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    response.end('<!doctype html><title>Preview test host</title>');
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(() => new Promise(resolve => { server.closeAllConnections?.(); server.close(resolve); }));
  const base = `http://127.0.0.1:${server.address().port}`;
  const html = successorPreviewDocument([file('game/successor/index.html', `<!-- <head> -->
    <img src="${base}/leaked-image"><script>
    fetch(${JSON.stringify(base + '/leaked-fetch')}).then(() => parent.postMessage({attempt: 'allowed'}, '*'), () => parent.postMessage({attempt: 'blocked'}, '*'));
    <\/script><head></head><body>Preview<script src="./game.js"></script></body>`),
    file('game/successor/game.js', "parent.postMessage({game: 'started'}, '*');"),
  ]);
  const browser = await runtime.chromium.launch({ executablePath: runtime.executablePath, headless: true, args: ['--no-sandbox'] });
  t.after(() => browser.close());
  const page = await browser.newPage();
  await page.goto(base + '/host');
  const outcome = await page.evaluate(html => new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Preview did not report its fetch result')), 5000);
    const observed = { result: null, game: null, origin: null };
    window.addEventListener('message', function handler(event) {
      if (event.data?.attempt) { observed.result = event.data.attempt; observed.origin = event.origin; }
      if (event.data?.game) observed.game = event.data.game;
      if (observed.result && observed.game) { clearTimeout(timer); window.removeEventListener('message', handler); resolve(observed); }
    });
    const frame = document.createElement('iframe'); frame.sandbox = 'allow-scripts'; frame.srcdoc = html; document.body.appendChild(frame);
  }), html);
  assert.deepEqual(outcome, { result: 'blocked', game: 'started', origin: 'null' });
  assert.deepEqual(requests.filter(url => url.startsWith('/leaked-')), []);
});

test('generated successor starts and responds to keyboard input in the actual isolated preview', {
  skip: runtime ? false : 'Requires a local Playwright installation and Chromium executable', timeout: 45000,
}, async t => {
  // This compiles an original temporary recipe through the real application
  // generator; it is not a canned HTML fixture or a claim about ROM support.
  const python = process.env.SKELETON_TEST_PYTHON || 'python3';
  const generator = spawnSync(python, ['-c', [
    'import json',
    'from skeleton.jeeves.game_successor import compile_successor, default_successor_profiles',
    "recipe = compile_successor(default_successor_profiles(), project_id='preview_test', title='Temporary preview test', seed=4)",
    "print(json.dumps([{'path': p, 'content': c} for p, c in recipe.files.items() if p.startswith('game/successor/')]))",
  ].join('\n')], { cwd: path.resolve(__dirname, '../..'), encoding: 'utf8', maxBuffer: 9 * 1024 * 1024 });
  if (generator.error?.code === 'ENOENT') { t.skip('Requires Python 3 to generate a successor'); return; }
  assert.equal(generator.status, 0, `Successor generation failed: ${generator.stderr}`);
  const html = successorPreviewDocument(JSON.parse(generator.stdout));
  assert.ok(html);
  const browser = await runtime.chromium.launch({ executablePath: runtime.executablePath, headless: true, args: ['--no-sandbox'] });
  t.after(() => browser.close());
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.setContent('<iframe sandbox="allow-scripts"></iframe>');
  await page.locator('iframe').evaluate((element, document) => { element.srcdoc = document; }, html);
  const frame = page.frameLocator('iframe');
  await frame.locator('#continue').click({ timeout: 15000 });
  const child = page.frames().find(value => value !== page.mainFrame());
  assert.ok(child);
  const before = await child.evaluate(() => window.SUCCESSOR_GAME.getState());
  await page.keyboard.down('ArrowRight');
  await page.waitForTimeout(600);
  await page.keyboard.up('ArrowRight');
  const after = await child.evaluate(() => window.SUCCESSOR_GAME.getState());
  assert.ok(after.steps > before.steps, 'The generated game loop must advance');
  assert.ok(after.x > before.x, 'A real ArrowRight key press must move the player');
  assert.deepEqual(errors, []);
});

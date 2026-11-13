'use strict';
// Real browser check of an actual ASGI response captured by the Python test.
// The local HTTP server is a transport fixture, not a generated-game proof.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');

function browserRuntime() {
  for (const name of ['playwright', '/opt/codex/runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright']) {
    try {
      const { chromium } = require(name);
      const executablePath = [process.env.CHROMIUM_EXECUTABLE_PATH, '/usr/bin/chromium', chromium.executablePath()]
        .find(value => value && fs.existsSync(value));
      if (executablePath) return { chromium, executablePath };
    } catch { /* Try another available local browser installation. */ }
  }
  return null;
}

(async () => {
  const runtime = browserRuntime();
  if (!runtime) { process.exitCode = 77; return; }
  const response = JSON.parse(fs.readFileSync(0, 'utf8'));
  const requests = [];
  const server = http.createServer((request, reply) => {
    requests.push(request.url);
    if (request.url === '/raw') {
      reply.writeHead(200, response.headers);
      reply.end(response.html);
    } else if (request.url === '/parent') {
      reply.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      reply.end('<!doctype html><title>application</title>');
    } else { reply.writeHead(204); reply.end(); }
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const base = 'http://127.0.0.1:' + server.address().port;
  const browser = await runtime.chromium.launch({ executablePath: runtime.executablePath, headless: true, args: ['--no-sandbox'] });
  try {
    const context = await browser.newContext();
    await context.addCookies([{ name: 'account_canary', value: 'private', url: base }]);
    const page = await context.newPage();
    await page.goto(base + '/parent');
    await page.evaluate(() => localStorage.setItem('private_app_canary', 'private'));
    await page.goto(base + '/raw');
    await page.waitForFunction(() => document.body.dataset.done === 'yes');
    const actual = await page.locator('body').getAttribute('data-result');
    assert.deepEqual(JSON.parse(actual), { scriptRan: true, cookieDenied: true, storageDenied: true, fetchDenied: true });
    assert.equal(requests.includes('/exfil'), false, 'Network access must be blocked before a request is sent');
    assert.equal((await context.cookies(base)).find(cookie => cookie.name === 'account_canary')?.value, 'private');
    await context.close();
    console.log('Direct HTML response ran scripts in an opaque, network-isolated sandbox');
  } finally {
    await browser.close();
    await new Promise(resolve => { server.closeAllConnections?.(); server.close(resolve); });
  }
})().catch(error => { console.error(error); process.exitCode = 1; });

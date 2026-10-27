'use strict';
// Execute the production postinstall hook against isolated copies of the
// actual reviewed dependency. No install, registry or network access is used.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { test } = require('node:test');

const ROOT = path.resolve(__dirname, '..');
const PATCHER = fs.readFileSync(path.join(__dirname, 'patch-node-modules.js'), 'utf8');
const PACKAGE = path.join(ROOT, 'node_modules/http-cache-semantics');
const VERSION = JSON.parse(fs.readFileSync(path.join(PACKAGE, 'package.json'), 'utf8')).version;
assert.equal(VERSION, '4.3.0', 'The behavior fixture must come from the reviewed installed version');
const VULNERABLE = 'if (allowsStaleWithoutRevalidation) {';
const HARDENED = 'if (allowsStaleWithoutRevalidation && this.maxAge() > 0) {';
const BASELINE = fs.readFileSync(path.join(PACKAGE, 'index.js'), 'utf8').replace(HARDENED, VULNERABLE);
assert.ok(BASELINE.includes(VULNERABLE), 'The reviewed max-stale branch must be present');

function fixture(t, { version = VERSION, source = BASELINE } = {}) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'http-cache-max-stale-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const script = path.join(root, 'scripts/patch-node-modules.js');
  const packagePath = path.join(root, 'node_modules/http-cache-semantics');
  const target = path.join(packagePath, 'index.js');
  fs.mkdirSync(path.dirname(script), { recursive: true }); fs.mkdirSync(packagePath, { recursive: true });
  fs.writeFileSync(script, PATCHER); fs.writeFileSync(path.join(packagePath, 'package.json'), JSON.stringify({ version })); fs.writeFileSync(target, source);
  return { target, run: () => spawnSync(process.execPath, [script], { cwd: root, encoding: 'utf8', timeout: 5000 }),
    policy() { delete require.cache[target]; return require(target); } };
}
function request(directive) {
  return { url: 'https://cache.example.test/private', method: 'GET',
    headers: { host: 'cache.example.test', ...(directive ? { 'cache-control': directive } : {}) } };
}
function zeroed(CachePolicy) {
  const policy = new CachePolicy(request(), { status: 200, headers: { date: new Date().toUTCString(), 'cache-control': 'max-age=60',
    'set-cookie': 'session=private-fixture; Secure; HttpOnly' } }, { shared: true });
  assert.equal(policy.maxAge(), 0, 'A shared Set-Cookie response has no reusable freshness');
  policy._responseTime -= 10_000; return policy;
}

test('the real 4.3.0 source reproduces max-stale resurrection before the postinstall guard', t => {
  const f = fixture(t), CachePolicy = f.policy();
  assert.equal(zeroed(CachePolicy).satisfiesWithoutRevalidation(request('max-stale=999999')), true);
  assert.equal(zeroed(CachePolicy).satisfiesWithoutRevalidation(request('max-stale')), true);
});

test('the production hook hardens 4.3.0 and blocks numeric and bare max-stale for zeroed responses', t => {
  const f = fixture(t), result = f.run();
  assert.equal(result.status, 0, result.stderr); assert.match(result.stdout, /security node_modules\/http-cache-semantics\/index\.js/);
  assert.ok(fs.readFileSync(f.target, 'utf8').includes(HARDENED));
  const CachePolicy = f.policy();
  assert.equal(zeroed(CachePolicy).satisfiesWithoutRevalidation(request('max-stale=999999')), false);
  assert.equal(zeroed(CachePolicy).satisfiesWithoutRevalidation(request('max-stale')), false);
});

test('legitimately cacheable public responses retain bounded max-stale behavior', t => {
  const f = fixture(t); assert.equal(f.run().status, 0);
  const CachePolicy = f.policy();
  const policy = new CachePolicy(request(), { status: 200,
    headers: { date: new Date().toUTCString(), 'cache-control': 'public, max-age=60' } }, { shared: true });
  assert.equal(policy.maxAge(), 60); policy._responseTime -= 90_000;
  assert.equal(policy.satisfiesWithoutRevalidation(request('max-stale=40')), true);
  assert.equal(policy.satisfiesWithoutRevalidation(request('max-stale=20')), false);
});

test('repeated install hooks leave the hardened source byte-identical', t => {
  const f = fixture(t); assert.equal(f.run().status, 0);
  const first = fs.readFileSync(f.target, 'utf8'), result = f.run();
  assert.equal(result.status, 0, result.stderr); assert.equal(fs.readFileSync(f.target, 'utf8'), first);
  assert.equal(first.split(HARDENED).length - 1, 1);
});

test('unreviewed package versions or changed branch shapes fail before source mutation', t => {
  for (const options of [{ version: '4.3.1' }, { source: BASELINE.replace(VULNERABLE, 'if (Boolean(allowsStaleWithoutRevalidation)) {') }]) {
    const f = fixture(t, options), before = fs.readFileSync(f.target, 'utf8'), result = f.run();
    assert.notEqual(result.status, 0); assert.match(result.stderr, /review required|requires security patch review/);
    assert.equal(fs.readFileSync(f.target, 'utf8'), before);
  }
});

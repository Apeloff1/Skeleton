'use strict';
// Independent locked archive verification. Do not execute any package code,
// extract into node_modules, rewrite the lockfile, or update a custody pin.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const { EXPECTED_VERSION, REVIEWED_UPSTREAM_SHA256, verifyReviewedForgeRsa } =
  require('./node-forge-rsa-custody.cjs');

const root = path.resolve(__dirname, '..');
const lock = fs.readFileSync(path.join(root, 'yarn.lock'), 'utf8');
const matches = [...lock.matchAll(/^node-forge@\^1\.3\.3:\r?\n((?:[ \t]+[^\r\n]+\r?\n)+)/gm)];
assert.equal(matches.length, 1, 'expected one frozen node-forge lock entry');
const stanza = matches[0][1];
const field = (name, pattern) => {
  const values = [...stanza.matchAll(new RegExp('^  ' + name + ' ' + pattern + '\\r?$', 'gm'))];
  assert.equal(values.length, 1, 'missing or ambiguous frozen ' + name);
  return values[0][1];
};
const version = field('version', '"([^"]+)"');
const resolved = field('resolved', '"([^"]+)"');
const integrity = field('integrity', '(sha512-[A-Za-z0-9+/]+={0,2})');
assert.equal(version, EXPECTED_VERSION);
const url = new URL(resolved);
assert.equal(url.origin, 'https://registry.yarnpkg.com');
assert.equal(url.pathname, '/node-forge/-/node-forge-' + EXPECTED_VERSION + '.tgz');
assert.equal(url.search, '');
assert.equal(url.username, '');
assert.equal(url.password, '');
assert.match(url.hash, /^#[a-f0-9]{40}$/);
const sha1 = url.hash.slice(1);
url.hash = '';

const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'forge-archive-custody-'));
try {
  // A fresh, isolated cache prevents accepting a stale installed package as
  // independent archive evidence. npm's package lifecycle is disabled.
  execFileSync('npm', ['pack', '--ignore-scripts', '--fetch-retries=1',
    '--fetch-timeout=60000', '--cache', path.join(temp, 'cache'),
    '--pack-destination', temp, '--', url.href],
  { stdio: ['ignore', 'pipe', 'pipe'], timeout: 180000, maxBuffer: 1024 * 1024 });
  const archive = path.join(temp, 'node-forge-' + EXPECTED_VERSION + '.tgz');
  const stat = fs.lstatSync(archive);
  assert.ok(stat.isFile() && stat.size > 0 && stat.size <= 16 * 1024 * 1024,
    'frozen archive must be a bounded regular file');
  const bytes = fs.readFileSync(archive);
  assert.equal('sha512-' + crypto.createHash('sha512').update(bytes).digest('base64'),
    integrity, 'frozen archive integrity mismatch; independent review required');
  assert.equal(crypto.createHash('sha1').update(bytes).digest('hex'), sha1,
    'frozen resolved archive identity mismatch');
  const tar = (args) => execFileSync('tar', args, {
    timeout: 15000, maxBuffer: 4 * 1024 * 1024,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  const members = tar(['-tzf', archive]).toString('utf8').split(/\r?\n/);
  for (const member of ['package/lib/rsa.js', 'package/package.json']) {
    assert.equal(members.filter(value => value === member).length, 1,
      'missing or ambiguous archive member: ' + member);
  }
  const raw = tar(['-xOzf', archive, 'package/lib/rsa.js']);
  const pkg = JSON.parse(tar(['-xOzf', archive, 'package/package.json']).toString('utf8'));
  assert.equal(pkg.version, EXPECTED_VERSION);
  assert.equal(crypto.createHash('sha256').update(raw).digest('hex'), REVIEWED_UPSTREAM_SHA256,
    'pristine RSA bytes differ from reviewed pin; stop for independent source review');
  const installed = fs.readFileSync(path.join(root, 'node_modules/node-forge/lib/rsa.js'));
  assert.ok(raw.equals(installed), 'installed RSA bytes differ from pristine archive');
  const text = raw.toString('utf8');
  assert.ok(raw.equals(Buffer.from(text, 'utf8')), 'RSA source is not canonical UTF-8');
  const proof = verifyReviewedForgeRsa(pkg.version, text);
  assert.equal(proof.patchRequired, false);
  assert.equal(proof.locallyPatched, false);
  console.log('[node-forge-archive] verified frozen tarball SHA-512, resolved SHA-1, raw RSA SHA-256 and installed bytes: ' + proof.rsaSha256);
} finally {
  fs.rmSync(temp, { recursive: true, force: true });
}

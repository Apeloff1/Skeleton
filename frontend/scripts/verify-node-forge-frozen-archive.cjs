'use strict';
// Independent locked archive verification. Never execute or rewrite the package.
// A supplied archive permits fully offline verification of exactly the same bytes.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const { EXPECTED_VERSION, REVIEWED_UPSTREAM_SHA256, verifyReviewedForgeRsa } =
  require('./node-forge-rsa-custody.cjs');
const { LOCK_LIMIT, ARCHIVE_LIMIT, RSA_LIMIT, readBoundedRegular, exactUtf8,
  parseFrozenForgeLock, verifyArchiveIdentity } = require('./node-forge-frozen-lock.cjs');

function main(args) {
  assert.ok(args.length === 0 ||
    (args.length === 2 && args[0] === '--archive' && args[1].length > 0),
    'usage: node verify-node-forge-frozen-archive.cjs [--archive /path/node-forge.tgz]');
  const root = path.resolve(__dirname, '..');
  const lockPath = path.join(root, 'yarn.lock');
  const lockBytes = readBoundedRegular(lockPath, LOCK_LIMIT);
  const lock = parseFrozenForgeLock(lockBytes);
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'forge-archive-custody-'));
  try {
    const snapshot = path.join(temp, 'verified.tgz');
    let bytes;
    if (args.length) {
      bytes = readBoundedRegular(path.resolve(args[1]), ARCHIVE_LIMIT);
    } else {
      // Fresh private cache; no lifecycle scripts and no npm package code.
      execFileSync('npm', ['pack', '--ignore-scripts', '--fetch-retries=1',
        '--fetch-timeout=60000', '--cache', path.join(temp, 'cache'),
        '--pack-destination', temp, '--', lock.url],
      { cwd: temp, stdio: ['ignore', 'pipe', 'pipe'], timeout: 180000,
        maxBuffer: 1024 * 1024 });
      bytes = readBoundedRegular(path.join(temp, 'node-forge-' + EXPECTED_VERSION + '.tgz'),
        ARCHIVE_LIMIT);
    }
    verifyArchiveIdentity(bytes, lock);
    // Parse only authenticated bytes from our private, exclusive snapshot.
    fs.writeFileSync(snapshot, bytes, { flag: 'wx', mode: 0o600 });
    const tar = (argv) => execFileSync('tar', argv, {
      timeout: 15000, maxBuffer: RSA_LIMIT, stdio: ['ignore', 'pipe', 'pipe'],
    });
    const members = exactUtf8(tar(['-tzf', snapshot])).split(/\r?\n/);
    for (const member of ['package/lib/rsa.js', 'package/package.json']) {
      assert.equal(members.filter(value => value === member).length, 1,
        'missing or ambiguous archive member: ' + member);
    }
    const raw = tar(['-xOzf', snapshot, 'package/lib/rsa.js']);
    const pkg = JSON.parse(exactUtf8(tar(['-xOzf', snapshot, 'package/package.json'])));
    assert.equal(pkg.version, EXPECTED_VERSION);
    assert.equal(crypto.createHash('sha256').update(raw).digest('hex'), REVIEWED_UPSTREAM_SHA256,
      'pristine RSA bytes differ from reviewed pin; stop for independent source review');
    const installedRoot = path.join(root, 'node_modules/node-forge');
    const installedPkg = JSON.parse(exactUtf8(readBoundedRegular(
      path.join(installedRoot, 'package.json'), 128 * 1024)));
    assert.equal(installedPkg.version, EXPECTED_VERSION, 'unreviewed installed version');
    const installed = readBoundedRegular(path.join(installedRoot, 'lib/rsa.js'), RSA_LIMIT);
    assert.ok(raw.equals(installed), 'installed RSA bytes differ from pristine archive');
    const proof = verifyReviewedForgeRsa(pkg.version, exactUtf8(raw));
    assert.equal(proof.patchRequired, false);
    assert.equal(proof.locallyPatched, false);
    assert.ok(lockBytes.equals(readBoundedRegular(lockPath, LOCK_LIMIT)), 'lockfile changed during proof');
    assert.ok(bytes.equals(readBoundedRegular(snapshot, ARCHIVE_LIMIT)), 'archive snapshot changed');
    console.log('[node-forge-archive] verified frozen SHA-512, resolved SHA-1, raw RSA SHA-256 and installed bytes: ' + proof.rsaSha256);
  } finally {
    fs.rmSync(temp, { recursive: true, force: true });
  }
}

if (require.main === module) main(process.argv.slice(2));
module.exports = { main };

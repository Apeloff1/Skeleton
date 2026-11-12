'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const {
  verifyReviewedForgeRsa, EXPECTED_VERSION, REVIEWED_UPSTREAM_SHA256,
} = require('./node-forge-rsa-custody.cjs');

const pkgPath = path.resolve(__dirname, '../node_modules/node-forge/package.json');
const rsaPath = path.resolve(__dirname, '../node_modules/node-forge/lib/rsa.js');

test('upstream 1.4.3 RSA implementation is byte-for-byte pinned, never rewritten', () => {
  const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf8'));
  const rsa = fs.readFileSync(rsaPath, 'utf8');
  assert.equal(pkg.version, EXPECTED_VERSION);
  assert.equal(
    crypto.createHash('sha256').update(rsa, 'utf8').digest('hex'),
    REVIEWED_UPSTREAM_SHA256,
  );
  const proof = verifyReviewedForgeRsa(pkg.version, rsa);
  assert.equal(proof.patchRequired, false);
  assert.equal(proof.locallyPatched, false);
  assert.equal(proof.securityDecision, 'reviewed_upstream_canonical_der');
  assert.equal(fs.readFileSync(rsaPath, 'utf8'), rsa);
});

test('patched, changed, truncated, mixed or unrecognized RSA source fails closed', () => {
  const source = fs.readFileSync(rsaPath, 'utf8');
  for (const bad of [
    source + '\n// unexpected extra code',
    source.replace(
      'd.substring(0, withParameters.length) !== withParameters &&',
      'false &&',
    ),
    source.replace(
      'var _encodeDigestInfo = function(oid, digest, withParameters)',
      'var _encodeDigestInfo = null',
    ),
    source.slice(0, source.length - 8),
  ]) {
    assert.throws(() => verifyReviewedForgeRsa(EXPECTED_VERSION, bad), /source differs/);
  }
  for (const unknown of ['1.4.2', '1.4.4', '1.4.0', '0.0.0', '']) {
    assert.throws(() => verifyReviewedForgeRsa(unknown, source), /unreviewed/);
  }
  assert.throws(() => verifyReviewedForgeRsa(EXPECTED_VERSION, null), /unreviewed/);
});

test('production Docker dependency stage includes the pinned RSA custody helper', () => {
  const dockerfile = fs.readFileSync(path.resolve(__dirname, '../Dockerfile'), 'utf8');
  const expected = 'COPY scripts/node-forge-rsa-custody.cjs ./scripts/node-forge-rsa-custody.cjs';
  const copyAt = dockerfile.indexOf(expected);
  const hookAt = dockerfile.indexOf('node ./scripts/patch-node-modules.js');
  assert.notEqual(copyAt, -1, 'source-pinned RSA verifier absent from container dependencies');
  assert.ok(hookAt > copyAt, 'security helper must precede install patch execution');
  assert.equal(dockerfile.split(expected).length, 2, 'Dockerfile must have exactly one RSA helper copy');
});

test('release npm guard invokes exact RSA custody and retains the hostile signature probe', () => {
  const security = fs.readFileSync(
    path.resolve(__dirname, 'verify-no-release-npm-security.js'), 'utf8',
  );
  assert.match(security, /verifyReviewedForgeRsa\(version, rsaSource\)/);
  assert.match(security, /version === '1\.4\.3'/);
  assert.match(security, /node-forge accepted nested DigestAlgorithm garbage/);
  assert.match(security, /_skipPaddingChecks: true/);
  assert.match(security, /receipt\.locallyPatched/);
  // Obsolete marker remains legal only inside a separately version-pinned
  // branch for the two older RSA implementations.
  assert.match(security, /version === '1\.4\.0' \|\| version === '1\.4\.2'/);
});

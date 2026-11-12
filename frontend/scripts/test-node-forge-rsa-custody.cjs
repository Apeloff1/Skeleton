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

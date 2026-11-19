'use strict';

/** The review target is upstream 1.4.3's immutable canonical-DER verifier.
 * Do NOT inject the obsolete 1.4.0/1.4.2 nested-arity source patch:
 * use exact upstream bytes, canonical ASN.1 anchors and a hostile signature
 * execution probe from verify-no-release-npm-security.js instead.
 */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { EXPECTED_VERSION, REVIEWED_UPSTREAM_SHA256, verifyReviewedForgeRsa } =
  require('./node-forge-rsa-custody.cjs');
const { qualifiesCanonicalRsaVerifier } =
  require('./security/node-forge-rsa-verifier.cjs');

test('locked node-forge RSA requires exact 1.4.3 custody with zero source writes', () => {
  const root = path.resolve(__dirname, '..');
  const lock = fs.readFileSync(path.join(root, 'yarn.lock'), 'utf8');
  const patch = fs.readFileSync(path.join(__dirname, 'patch-node-modules.js'), 'utf8');
  assert.equal(EXPECTED_VERSION, '1.4.3');
  assert.match(lock, /node-forge-1\.4\.3\.tgz/);
  assert.match(patch, /version !== '1\.4\.3'/);
  assert.match(patch, /node-forge \$\{version\} requires security patch review/);
  assert.match(patch, /verifyReviewedForgeRsa\(version, original\)/);
  assert.match(patch, /receipt\.patchRequired !== false/);
  assert.match(patch, /receipt\.locallyPatched !== false/);
  const start = patch.indexOf('function patchNodeForgeNestedDigestAlgorithm(');
  const end = patch.indexOf('\nfunction patchSprintfFormatBounds(', start);
  assert.ok(start >= 0 && end > start, 'source custody code must exist');
  assert.doesNotMatch(patch.slice(start, end), /fs\.writeFileSync\(/,
    'reviewed upstream RSA bytes may not be rewritten by postinstall');
});

test('actual installed RSA bytes implement strict canonical DER without a local patch', () => {
  const root = path.resolve(__dirname, '..');
  const resolved = require.resolve('node-forge/package.json', { paths: [root] });
  const pkg = JSON.parse(fs.readFileSync(resolved, 'utf8'));
  assert.equal(pkg.version, EXPECTED_VERSION);
  const original = fs.readFileSync(path.join(path.dirname(resolved), 'lib/rsa.js'), 'utf8');
  const digest = crypto.createHash('sha256').update(original, 'utf8').digest('hex');
  assert.equal(digest, REVIEWED_UPSTREAM_SHA256);
  const receipt = verifyReviewedForgeRsa(pkg.version, original);
  assert.equal(receipt.locallyPatched, false);
  assert.equal(receipt.patchRequired, false);
  assert.equal(receipt.securityDecision, 'reviewed_upstream_canonical_der');
  assert.equal(qualifiesCanonicalRsaVerifier(original), true);
  for (const changed of [
    original + '\n//unreviewed patch',
    original.replace('obj.value.length !== 2', 'obj.value.length > 2'),
    original.replace('parseAllBytes: options._parseAllDigestBytes', 'parseAllBytes: false'),
    original.slice(0, -8),
  ]) {
    assert.throws(() => verifyReviewedForgeRsa(pkg.version, changed), /source differs/);
  }
  assert.equal(fs.readFileSync(path.join(path.dirname(resolved), 'lib/rsa.js'), 'utf8'), original);
});

'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { qualifiesCanonicalRsaVerifier } = require('./security/node-forge-rsa-verifier.cjs');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');

// Bounded fingerprint of the actual published v1.4.3 RSA verifier, without
// executing third-party crypto code or trusting a version-string assertion.
const canonical = `
var _encodeDigestInfo = function(oid, digest, withParameters) {
  return asn1.toDer(asn1.create(asn1.Class.UNIVERSAL, asn1.Type.SEQUENCE, true, []));
};
${'x'.repeat(1200)}
var obj = asn1.fromDer(d, {
  parseAllBytes: options._parseAllDigestBytes
});
var capture = {};
var errors = [];
if(!asn1.validate(obj, digestInfoValidator, capture, errors) ||
  obj.value.length !== 2) {
  throw new Error('Malformed DigestInfo');
}
var oid = asn1.derToOid(capture.algorithmIdentifier);
var withParameters = _encodeDigestInfo(oid, capture.digest, true);
var withoutParameters =
  _encodeDigestInfo(oid, capture.digest, false);
if(d.substring(0, withParameters.length) !== withParameters &&
  d.substring(0, withoutParameters.length) !== withoutParameters) {
  throw new Error('Noncanonical DER');
}
return digest === capture.digest;
`;
test('reviewed 1.4.3 RSA canonical-DER verifier qualifies by source contract', () => {
  assert.equal(qualifiesCanonicalRsaVerifier(canonical), true);
});
test('missing or altered security checks cannot enter the frontend image', () => {
  const mutations = [
    canonical.replace('obj.value.length !== 2', 'obj.value.length >= 2'),
    canonical.replace('parseAllBytes: options._parseAllDigestBytes', 'parseAllBytes: false'),
    canonical.replace('var withoutParameters =', 'const ignoreParameters ='),
    canonical.replace('d.substring(0, withParameters.length)', 'true'),
    canonical.replace('return digest === capture.digest;', 'return true;'),
    canonical.replace('if(!asn1.validate', 'if(asn1.validate'),
    canonical.replace('var _encodeDigestInfo', 'var _notCanonical'),
    canonical.replace('if(d.substring', 'return digest === capture.digest;\nif(d.substring'),
    canonical + '\n// skeleton GHSA-86w9-cpqp-85rv',
    canonical + '\nobj.value[0].value.length !== 2',
    'node-forge 1.4.3',
  ];
  for (const input of mutations) {
    assert.equal(qualifiesCanonicalRsaVerifier(input), false,
      'unreviewed RSA verifier must block the Docker dependency patch stage');
  }
});

test('frontend Docker dependency layer copies immutable RSA custody before postinstall', () => {
  const docker = readFileSync(join(__dirname, '..', 'Dockerfile'), 'utf8');
  const patch = readFileSync(join(__dirname, 'patch-node-modules.js'), 'utf8');
  const exact = 'COPY scripts/node-forge-rsa-custody.cjs ./scripts/node-forge-rsa-custody.cjs';
  const copyAt = docker.indexOf(exact);
  const installAt = docker.indexOf('node ./scripts/patch-node-modules.js');
  assert.ok(copyAt >= 0 && installAt > copyAt, 'reviewed source must be pinned before postinstall');
  assert.equal(docker.split(exact).length, 2, 'custody helper must be copied exactly once');
  assert.match(patch, /require\('\.\/node-forge-rsa-custody\.cjs'\)/);
  assert.match(patch, /verifyReviewedForgeRsa\(version, original\)/);
  assert.match(patch, /receipt\.securityDecision !== 'reviewed_upstream_canonical_der'/);
  const begin = patch.indexOf('function patchNodeForgeNestedDigestAlgorithm(');
  const end = patch.indexOf('\nfunction patchSprintfFormatBounds(', begin);
  assert.ok(begin >= 0 && end > begin, 'bounded RSA postinstall admission function required');
  assert.doesNotMatch(patch.slice(begin, end), /fs\.writeFileSync\(/,
    'a newer pinned canonical DER implementation must never be rewritten');
});

test('release security smoke executes hostile signature denial and exact pinned RSA byte custody', () => {
  const script = readFileSync(join(__dirname, 'verify-no-release-npm-security.js'), 'utf8');
  const custody = readFileSync(join(__dirname, 'node-forge-rsa-custody.cjs'), 'utf8');
  assert.match(script, /node-forge accepted nested DigestAlgorithm garbage/);
  assert.match(script, /_parseAllDigestBytes: true/);
  assert.match(script, /_skipPaddingChecks: true/);
  assert.match(script, /version === '1\.4\.3'/);
  assert.match(script, /verifyReviewedForgeRsa\(version, rsaSource\)/);
  assert.match(script, /receipt\.locallyPatched/);
  assert.match(script, /node-forge 1\.4\.3 canonical-DER source custody is not verified/);
  assert.match(script, /node-forge nested DigestAlgorithm source guard is missing/);
  assert.match(custody, /crypto\.createHash\('sha256'\)\.update\(source, 'utf8'\)\.digest\('hex'\)/);
  assert.match(custody, /digest !== REVIEWED_UPSTREAM_SHA256/);
  assert.match(custody, /source\.split\(value\)\.length !== 2/);
  assert.match(custody, /patchRequired: false/);
  assert.match(custody, /locallyPatched: false/);
});

'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { qualifiesCanonicalRsaVerifier } = require('./security/node-forge-rsa-verifier.cjs');

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

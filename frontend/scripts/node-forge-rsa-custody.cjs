'use strict';
/**
 * Reviewed immutable upstream RSA source custody for node-forge 1.4.3.
 *
 * The repo's legacy 1.4.0/1.4.2 local DigestInfo patch must NOT be injected
 * into a newer audited upstream implementation: doing so could corrupt or
 * weaken the canonical-DER verification added in 1.4.1.
 *
 * This is a version + exact-source SHA pin, not semver trust or a regex-only
 * waiver. Reject missing, mixed, modified and unrecognized source code.
 */
const crypto = require('node:crypto');

const EXPECTED_VERSION = '1.4.3';
// Exact upstream digitalbazaar/forge v1.4.3 lib/rsa.js SHA-256,
// obtained from the published GitHub tag; independently recheck npm tarball
// before final security/release qualification.
const REVIEWED_UPSTREAM_SHA256 = '6632e195295ce76f6bb9131ee770dcd6cc1ee4ffac7906302208b00faf95a87f';

function verifyReviewedForgeRsa(version, source) {
  if (version !== EXPECTED_VERSION || typeof source !== 'string') {
    throw new Error('[node-forge] unreviewed version or missing RSA implementation');
  }
  const digest = crypto.createHash('sha256').update(source, 'utf8').digest('hex');
  if (digest !== REVIEWED_UPSTREAM_SHA256) {
    throw new Error('[node-forge] upstream RSA source differs from reviewed 1.4.3 tag');
  }
  // Defence-in-depth: these anchors document the specific canonicalization
  // semantics that the byte-for-byte pin commits to. They do not replace it.
  const required = [
    'var _encodeDigestInfo = function(oid, digest, withParameters)',
    'var withParameters = _encodeDigestInfo(oid, capture.digest, true);',
    '_encodeDigestInfo(oid, capture.digest, false);',
    'd.substring(0, withParameters.length) !== withParameters &&',
    'd.substring(0, withoutParameters.length) !== withoutParameters',
    'asn1.fromDer(d, {',
    'parseAllBytes: options._parseAllDigestBytes',
  ];
  for (const value of required) {
    if (source.split(value).length !== 2) {
      throw new Error('[node-forge] RSA canonical-DER verify path missing or ambiguous');
    }
  }
  return Object.freeze({
    version: EXPECTED_VERSION,
    rsaSha256: digest,
    securityDecision: 'reviewed_upstream_canonical_der',
    patchRequired: false,
    locallyPatched: false,
  });
}

module.exports = {
  verifyReviewedForgeRsa,
  EXPECTED_VERSION,
  REVIEWED_UPSTREAM_SHA256,
};

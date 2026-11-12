'use strict';
/**
 * Structure-based source qualification for the node-forge 1.4.3 canonical
 * DER RSA PKCS#1 v1.5 verifier. A semver bump is NOT a security patch.
 *
 * Reject missing/reordered/mixed guards instead of silently bypassing an
 * existing fail-closed third-party patch. No dependency is executed here.
 */
const GUARDS = Object.freeze([
  /var _encodeDigestInfo = function\(oid, digest, withParameters\) \{/,
  /parseAllBytes: options\._parseAllDigestBytes/,
  /if\(!asn1\.validate\(obj, digestInfoValidator, capture, errors\) \|\|\s*obj\.value\.length !== 2\)/,
  /var withParameters = _encodeDigestInfo\(oid, capture\.digest, true\);/,
  /var withoutParameters =\s*_encodeDigestInfo\(oid, capture\.digest, false\);/,
  /if\(d\.substring\(0, withParameters\.length\) !== withParameters &&\s*d\.substring\(0, withoutParameters\.length\) !== withoutParameters\)/,
]);
function qualifiesCanonicalRsaVerifier(source) {
  if (typeof source !== 'string' || source.length < 1000 || source.length > 400000
      || source.includes('skeleton GHSA-86w9-cpqp-85rv')
      || source.includes('obj.value[0].value.length !==')) return false;
  const check = GUARDS.map(pattern => pattern.exec(source));
  if (check.some(match => !match)) return false;
  // The decoder must validate ASN.1 and reject malformed nested DER before
  // declaring digest equality; a guard moved after return is not protection.
  const order = check.map(match => match.index);
  return order[0] < order[1] && order[1] < order[2] &&
    order[2] < order[3] && order[3] < order[4] && order[4] < order[5] &&
    source.indexOf('return digest === capture.digest;', order[2]) > order[5];
}
module.exports = { qualifiesCanonicalRsaVerifier };

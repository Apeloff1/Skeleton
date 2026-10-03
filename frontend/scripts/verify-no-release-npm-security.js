#!/usr/bin/env node
/* eslint-disable */
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const ROOT = path.resolve(__dirname, '..');

function verifyBracesDepthGuard() {
  const source = [
    "const braces = require('braces');",
    "const input = '{'.repeat(5000) + 'a,b' + '}'.repeat(5000);",
    "const output = braces(input);",
    "if (!Array.isArray(output) || output.length !== 1 || output[0] !== input) process.exit(7);",
  ].join('\n');
  const result = spawnSync(process.execPath, ['-e', source], {
    cwd: ROOT,
    encoding: 'utf8',
    timeout: 2000,
  });
  if (result.error && result.error.code === 'ETIMEDOUT') {
    throw new Error('braces nested-pattern mitigation timed out');
  }
  if (result.error) throw result.error;
  if (result.status !== 0) {
    throw new Error(
      `braces nested-pattern mitigation failed: status=${result.status} stderr=${result.stderr}`,
    );
  }
}

function verifyHttpCacheMaxStaleGuard() {
  const CachePolicy = require('http-cache-semantics');
  const request = {
    url: 'https://cache.example.test/private',
    method: 'GET',
    headers: { host: 'cache.example.test' },
  };
  const response = {
    status: 200,
    headers: {
      date: new Date().toUTCString(),
      'cache-control': 'max-age=60',
      'set-cookie': 'session=private-secret; Secure; HttpOnly',
    },
  };
  const policy = new CachePolicy(request, response, { shared: true });

  // Make the zeroed shared response stale. maxAge() is forced to zero for
  // shared Set-Cookie responses unless they explicitly opt into public caching.
  policy._responseTime -= 10_000;

  const attackerRequest = {
    ...request,
    headers: {
      host: 'cache.example.test',
      'cache-control': 'max-stale=999999',
    },
  };
  if (policy.satisfiesWithoutRevalidation(attackerRequest)) {
    throw new Error('http-cache-semantics reused a security-zeroed response via max-stale');
  }
}

function verifyNodeForgeNestedDigestAlgorithmGuard() {
  const forge = require('node-forge');
  const BigInteger = forge.jsbn.BigInteger;

  const nHex =
    'E932AC92252F585B3A80A4DD76A897C8B7652952FE788F6EC8DD640587A1EE56' +
    '47670A8AD4C2BE0F9FA6E49C605ADF77B5174230AF7BD50E5D6D6D6D28CCF0A8' +
    '86A514CC72E51D209CC772A52EF419F6A953F3135929588EBE9B351FCA61CED7' +
    '8F346FE00DBB6306E5C2A4C6DFC3779AF85AB417371CF34D8387B9B30AE46D7A' +
    '5FF5A655B8D8455F1B94AE736989D60A6F2FD5CADBFFBD504C5A756A2E6BB5CE' +
    'CC13BCA7503F6DF8B52ACE5C410997E98809DB4DC30D943DE4E812A47553DCE5' +
    '4844A78E36401D13F77DC650619FED88D8B3926E3D8E319C80C744779AC5D6AB' +
    'E252896950917476ECE5E8FC27D5F053D6018D91B502C4787558A002B9283DA7';

  // Upstream digitalbazaar/forge #1152 regression fixture for CVE-2026-85393.
  const signatureHex =
    'a4ae63dd5e7712b78f4870d0f51e294df5503d4f16c5d27ae33370981fb57f0de49f' +
    '50f3d6a04666774cd984cd13972db9bf8e12bd294ef0ddc916c7c86cbae63efd7b6b' +
    '97885e69760c208a40f1aecc76a90d7af5145177efce1bb55807a8d05c20b1596753' +
    'ba710642fc9acdde6c160232654662c77cc4466c8257a38edb49f894e8845d0fd987' +
    'b857ced88f4b62505a080bd87ef700d35d392a6e8f6fde34250c50b86fae606cb551' +
    '215e8f4813239b77651d5565ad453698c071d48c31e8e526fb4a37610f64b3e1fb8e' +
    '5be5898e408ad08197a0947794a530b54f84485377ce4a7488ed485ce4e5e105dd89' +
    '698a472f390c3b1b76bc16b73276c4d1c81d';

  const publicKey = forge.pki.rsa.setPublicKey(
    new BigInteger(nHex, 16),
    new BigInteger('3'),
  );
  const md = forge.md.sha256.create();
  md.update('hello world!');

  let rejected = false;
  try {
    publicKey.verify(
      md.digest().getBytes(),
      forge.util.hexToBytes(signatureHex),
      undefined,
      {
        _parseAllDigestBytes: true,
        _skipPaddingChecks: true,
      },
    );
  } catch (error) {
    rejected = true;
  }
  if (!rejected) {
    throw new Error('node-forge accepted nested DigestAlgorithm garbage');
  }

  const rsaPath = require.resolve('node-forge/lib/rsa');
  const rsaSource = fs.readFileSync(rsaPath, 'utf8');
  if (!rsaSource.includes('obj.value[0].value.length !==')) {
    throw new Error('node-forge nested DigestAlgorithm source guard is missing');
  }
}

verifyBracesDepthGuard();
verifyHttpCacheMaxStaleGuard();
verifyNodeForgeNestedDigestAlgorithmGuard();

console.log(
  '[verify-no-release-npm-security] braces, http-cache-semantics, and node-forge mitigations verified',
);

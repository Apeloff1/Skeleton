'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

test('locked node-forge 1.4.3 retains the reviewed exact-version RSA patch policy', () => {
  const root = path.resolve(__dirname, '..');
  const lock = fs.readFileSync(path.join(root, 'yarn.lock'), 'utf8');
  assert.match(lock, /node-forge-1\.4\.3\.tgz/);
  const securityPatcher = fs.readFileSync(path.join(__dirname, 'patch-node-modules.js'), 'utf8');
  assert.match(securityPatcher, /version !== '1\.4\.3'/);
  assert.match(securityPatcher, /node-forge \$\{version\} requires security patch review/);
  assert.match(securityPatcher, /obj\\\.value\\\[0\\\]\\\.value\\\.length/);
});

test('postinstall RSA verifier rejects unpatched nested algorithm lengths', () => {
  const root = path.resolve(__dirname, '..');
  const resolved = require.resolve('node-forge/package.json', { paths: [root] });
  const pkg = JSON.parse(fs.readFileSync(resolved, 'utf8'));
  assert.equal(pkg.version, '1.4.3');
  const rsa = fs.readFileSync(path.join(path.dirname(resolved), 'lib/rsa.js'), 'utf8');
  const hardened = /obj\.value\[0\]\.value\.length !==/g;
  const matches = [...rsa.matchAll(hardened)];
  assert.equal(matches.length, 1, 'must admit one nested DigestAlgorithm arity check');
  assert.match(rsa, /\('parameters' in capture\) \? 2 : 1/);
  assert.doesNotMatch(rsa,
    /if\(!asn1\.validate\(obj, digestInfoValidator, capture, errors\) \|\|\s*obj\.value\.length !== 2\) \{/);
});

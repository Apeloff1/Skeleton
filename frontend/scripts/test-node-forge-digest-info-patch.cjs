'use strict';
// Preserve the historical CI entrypoint, but validate the admitted upstream
// implementation instead of requiring a now-obsolete postinstall rewrite.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { verifyReviewedForgeRsa } = require('./node-forge-rsa-custody.cjs');

test('frozen node-forge 1.4.3 uses exact reviewed upstream RSA bytes', () => {
  const root = path.resolve(__dirname, '..');
  const lock = fs.readFileSync(path.join(root, 'yarn.lock'), 'utf8');
  assert.match(lock, /node-forge-1\.4\.3\.tgz/);
  const pkgPath = require.resolve('node-forge/package.json', {paths: [root]});
  const version = JSON.parse(fs.readFileSync(pkgPath, 'utf8')).version;
  assert.equal(version, '1.4.3');
  const rsa = fs.readFileSync(path.join(path.dirname(pkgPath), 'lib/rsa.js'), 'utf8');
  assert.doesNotThrow(() => verifyReviewedForgeRsa(version, rsa));
  assert.throws(() => verifyReviewedForgeRsa(version, rsa + '\n'));
  assert.throws(() => verifyReviewedForgeRsa('1.4.2', rsa));
});

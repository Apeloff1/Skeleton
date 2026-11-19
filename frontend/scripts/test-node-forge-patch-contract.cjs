'use strict';

// Isolated tests execute the production postinstall function. The mock below
// models the reviewed helper's accept/deny decision; separate custody tests
// hash the ACTUAL installed upstream 1.4.3 bytes and execute hostile probes.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, 'patch-node-modules.js'), 'utf8');

const start = source.indexOf('function patchNodeForgeNestedDigestAlgorithm(');
const end = source.indexOf('\nfunction patchSprintfFormatBounds(', start);
assert.ok(start >= 0 && end > start);
const patchForge = source.slice(start, end);
const REVIEWED = 'reviewed-upstream-rsa-fixture-only';
assert.match(source, /require\('\.\/node-forge-rsa-custody\.cjs'\)/);
assert.doesNotMatch(patchForge, /fs\.writeFileSync\(/);

function fixture(t, version = '1.4.3', contents = REVIEWED) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'skeleton-immutable-forge-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const directory = path.join(root, 'node_modules', 'node-forge');
  fs.mkdirSync(path.join(directory, 'lib'), { recursive: true });
  fs.writeFileSync(path.join(directory, 'package.json'), JSON.stringify({ version }));
  const filename = path.join(directory, 'lib', 'rsa.js');
  fs.writeFileSync(filename, contents);
  let checked = 0;
  const verifyReviewedForgeRsa = (v, bytes) => {
    checked++;
    if (v !== '1.4.3' || bytes !== REVIEWED) {
      throw new Error('[node-forge] upstream RSA source differs from reviewed 1.4.3 tag');
    }
    return {
      patchRequired: false,
      locallyPatched: false,
      securityDecision: 'reviewed_upstream_canonical_der',
    };
  };
  const worker = vm.runInNewContext(
    'let patched = 0; let skipped = 0;\n' + patchForge +
    '\n({ run: patchNodeForgeNestedDigestAlgorithm, counters: () => ({ patched, skipped }) })',
    { fs, path, ROOT: root, verifyReviewedForgeRsa, console: { log() {} } },
    { timeout: 1000 },
  );
  return {
    run: () => worker.run(),
    read: () => fs.readFileSync(filename, 'utf8'),
    path: filename,
    checks: () => checked,
    counters: () => ({ ...worker.counters() }),
  };
}

test('reviewed 1.4.3 RSA bytes remain unchanged across repeated postinstall', t => {
  const f = fixture(t);
  f.run();
  f.run();
  assert.equal(f.read(), REVIEWED);
  assert.equal(f.checks(), 2);
  assert.equal(f.counters().patched, 0);
  assert.equal(f.counters().skipped, 2);
});

for (const version of ['1.4.0', '1.4.1', '1.4.2', '1.4.4', '1.5.0']) {
  test('unreviewed node-forge ' + version + ' fails without mutation', t => {
    const f = fixture(t, version);
    assert.throws(f.run, /requires security patch review/);
    assert.equal(f.read(), REVIEWED);
    assert.equal(f.counters().patched, 0);
    assert.equal(f.checks(), 0);
  });
}

for (const tampered of [
  'function verify() { return true; }',
  REVIEWED + '\n// unreviewed local patch',
  REVIEWED.slice(0, -1),
  REVIEWED + '\nobj.value[0].value.length !==',
]) {
  test('modified RSA source fails custody and is never rewritten', t => {
    const f = fixture(t, '1.4.3', tampered);
    assert.throws(f.run, /source differs/);
    assert.equal(f.read(), tampered);
    assert.equal(f.counters().patched, 0);
  });
}

test('symlinked node-forge RSA artifact fails before source acceptance', t => {
  const f = fixture(t);
  const original = f.path + '.original';
  fs.renameSync(f.path, original);
  fs.symlinkSync(original, f.path);
  assert.throws(f.run, /original regular file/);
  assert.equal(fs.readFileSync(original, 'utf8'), REVIEWED);
  assert.equal(f.checks(), 0);
});

test('hardlinked RSA artifact cannot masquerade as original isolated source', t => {
  const f = fixture(t);
  fs.linkSync(f.path, f.path + '.alias');
  assert.throws(f.run, /original regular file/);
  assert.equal(f.read(), REVIEWED);
  assert.equal(f.checks(), 0);
});

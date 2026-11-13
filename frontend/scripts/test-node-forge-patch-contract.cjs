'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const vm = require('node:vm');

// Run the production hardener itself in an isolated fixture rather than
// copying or approximating its logic. No installed packages or network needed.
const source = fs.readFileSync(path.join(__dirname, 'patch-node-modules.js'), 'utf8');

function extract(start, end) {
  const from = source.indexOf(start);
  const to = source.indexOf(end, from);
  assert.ok(from >= 0 && to > from, 'production source contract changed: ' + start);
  return source.slice(from, to);
}

const patchHelper = extract('function patchSecurityFile(', '\nfunction patchImageSizeDoS(');
const patchForge = extract('function patchNodeForgeNestedDigestAlgorithm(', '\nfunction patchSprintfFormatBounds(');
const vulnerable = [
  'function verify() {',
  '  if(!asn1.validate(obj, digestInfoValidator, capture, errors) ||',
  '    obj.value.length !== 2) {',
  "    throw new Error('invalid DigestInfo');",
  '  }',
  '}',
  '',
].join('\n');

function fixture(t, version, rsaSource = vulnerable) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'skeleton-forge-policy-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const dir = path.join(root, 'node_modules', 'node-forge');
  fs.mkdirSync(path.join(dir, 'lib'), { recursive: true });
  fs.writeFileSync(path.join(dir, 'package.json'),
    JSON.stringify({ name: 'node-forge', version }), 'utf8');
  const rsaPath = path.join(dir, 'lib', 'rsa.js');
  fs.writeFileSync(rsaPath, rsaSource, 'utf8');
  const harness = vm.runInNewContext(
    'let patched = 0; let skipped = 0;\n' +
      patchHelper + '\n' + patchForge +
      '\n({ run: patchNodeForgeNestedDigestAlgorithm, counters: () => ({ patched, skipped }) })',
    { fs, path, ROOT: root, console: { log() {} } }, { timeout: 1000 });
  return {
    run: () => harness.run(),
    read: () => fs.readFileSync(rsaPath, 'utf8'),
    counters: () => ({ ...harness.counters() }),
  };
}

test('1.4.3 applies the original nested-arity mitigation exactly once', t => {
  const target = fixture(t, '1.4.3');
  target.run();
  const patched = target.read();
  assert.match(patched, /obj\.value\[0\]\.value\.length !==/);
  assert.match(patched, /\(\('parameters' in capture\) \? 2 : 1\)/);
  assert.doesNotMatch(patched,
    /obj\.value\.length !== 2\) \{/);
  assert.equal(target.counters().patched, 1);
  target.run();
  assert.equal(target.read(), patched);
  assert.equal(target.counters().patched, 1);
  assert.equal(target.counters().skipped, 1);
});

for (const version of ['1.4.0', '1.4.2']) {
  test('legacy reviewed node-forge ' + version + ' remains hardened', t => {
    const target = fixture(t, version);
    target.run();
    assert.match(target.read(), /obj\.value\[0\]\.value\.length !==/);
    assert.equal(target.counters().patched, 1);
  });
}

for (const version of ['1.4.1', '1.4.4', '1.5.0']) {
  test('unreviewed node-forge ' + version + ' fails before modification', t => {
    const target = fixture(t, version);
    assert.throws(target.run, /requires security patch review/);
    assert.equal(target.read(), vulnerable);
    assert.equal(target.counters().patched, 0);
  });
}

test('changed upstream RSA parser shape fails closed', t => {
  const unrecognized = 'function verify() { return true; }\n';
  const target = fixture(t, '1.4.3', unrecognized);
  assert.throws(target.run, /security target changed shape/);
  assert.equal(target.read(), unrecognized);
});

test('mixed hardening markers and vulnerable guard fail closed', t => {
  const mixed = vulnerable + '\n// obj.value[0].value.length !==\n';
  const target = fixture(t, '1.4.3', mixed);
  assert.throws(target.run, /mixed DigestInfo patch states/);
  assert.equal(target.read(), mixed);
});

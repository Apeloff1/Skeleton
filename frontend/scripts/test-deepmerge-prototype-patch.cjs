'use strict';
// Run the production postinstall hook only on isolated copies of the exact
// installed upstream package. No install or live node_modules mutation.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { test } = require('node:test');

const frontend = path.resolve(__dirname, '..');
const original = path.join(frontend, 'node_modules/deepmerge');
const patcher = fs.readFileSync(path.join(__dirname, 'patch-node-modules.js'), 'utf8');
const verifier = fs.readFileSync(path.join(__dirname, 'verify-deepmerge-security.cjs'), 'utf8');
const files = ['index.js', 'dist/cjs.js', 'dist/umd.js'];
assert.equal(JSON.parse(fs.readFileSync(path.join(original, 'package.json'), 'utf8')).version, '4.3.1');

function fixture(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'deepmerge-prototype-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const script = path.join(root, 'scripts/patch-node-modules.js');
  const pkg = path.join(root, 'node_modules/deepmerge');
  fs.mkdirSync(path.dirname(script), { recursive: true });
  fs.cpSync(original, pkg, { recursive: true });
  fs.writeFileSync(script, patcher);
  const verifyScript = path.join(root, 'scripts/verify-deepmerge-security.cjs');
  fs.writeFileSync(verifyScript, verifier);
  // index.js expects an upstream dev dependency that the shipped dist bundles
  // inline. This fixture covers the same ordinary/null-prototype input shapes.
  const dep = path.join(root, 'node_modules/is-mergeable-object');
  fs.mkdirSync(dep, { recursive: true });
  fs.writeFileSync(path.join(dep, 'index.js'), "module.exports = v => !!v && typeof v === 'object' && !(v instanceof Date) && !(v instanceof RegExp);\n");
  const expo = path.join(root, 'node_modules/@expo/config');
  fs.mkdirSync(expo, { recursive: true });
  fs.writeFileSync(path.join(expo, 'package.json'), JSON.stringify({ name: '@expo/config', version: '12.0.14' }));
  return {
    pkg,
    run: () => spawnSync(process.execPath, [script], { cwd: root, encoding: 'utf8', timeout: 5000 }),
    verify: () => spawnSync(process.execPath, [verifyScript], { cwd: root, encoding: 'utf8', timeout: 5000 }),
    load(rel) { const target = path.join(pkg, rel); delete require.cache[target]; return require(target); },
    snapshot: () => files.map(rel => fs.readFileSync(path.join(pkg, rel), 'utf8')),
  };
}

function maliciousTarget() { return JSON.parse('{"__proto__":{"polluted":"from-target"},"safe":1}'); }
function maliciousSource() { return JSON.parse('{"__proto__":{"polluted":"from-source"},"safe":2}'); }

test('real upstream distributions reproduce poisoning before mitigation', t => {
  const f = fixture(t);
  for (const rel of files) {
    const merge = f.load(rel);
    assert.equal(merge(maliciousTarget(), {}).polluted, 'from-target', rel);
    assert.equal(merge(Object.create(null), maliciousSource()).polluted, 'from-source', rel);
  }
});

test('postinstall rejects target and source poisoning in all three distributions', t => {
  const f = fixture(t);
  assert.notEqual(f.verify().status, 0, 'the production verifier must reject unpatched packages');
  const result = f.run();
  assert.equal(result.status, 0, result.stderr);
  assert.equal(f.verify().status, 0, 'the verifier must accept the actually hardened package');
  for (const rel of files) {
    const merge = f.load(rel);
    assert.throws(() => merge(maliciousTarget(), {}), /unsafe __proto__ key/, rel);
    assert.throws(() => merge(Object.create(null), maliciousSource()), /unsafe __proto__ key/, rel);
    const symbol = Symbol('retained');
    const output = merge({ a: [1], nested: { x: 1 }, [symbol]: 'kept' }, { a: [2], nested: { y: 2 } });
    assert.deepEqual(output.a, [1, 2]);
    assert.deepEqual(output.nested, { x: 1, y: 2 });
    assert.equal(output[symbol], 'kept');
    const special = Symbol.for('__proto__');
    assert.equal(merge({ [special]: 'symbol value' }, {})[special], 'symbol value');
    assert.deepEqual(merge({ constructor: { label: 'ordinary data' } }, {}).constructor,
      { label: 'ordinary data' });
    assert.throws(() => merge({ nested: [maliciousTarget()] }, {}), /unsafe __proto__ key/, rel);
    assert.throws(() => merge({ nested: {} }, { nested: maliciousSource() }), /unsafe __proto__ key/, rel);
  }
  assert.equal({}.polluted, undefined);
});

test('postinstall is idempotent', t => {
  const f = fixture(t);
  assert.equal(f.run().status, 0);
  const first = f.snapshot();
  assert.equal(f.run().status, 0);
  assert.deepEqual(f.snapshot(), first);
});

test('an interrupted multi-file update can be rerun without changing hardened files', t => {
  const f = fixture(t);
  assert.equal(f.run().status, 0);
  const hardened = f.snapshot();
  fs.copyFileSync(path.join(original, files[0]), path.join(f.pkg, files[0]));
  assert.equal(f.run().status, 0);
  assert.deepEqual(f.snapshot(), hardened);
});

test('version drift and partial guard state fail before any file is changed', t => {
  const f = fixture(t), pkgJson = path.join(f.pkg, 'package.json');
  const meta = JSON.parse(fs.readFileSync(pkgJson, 'utf8'));
  fs.writeFileSync(pkgJson, JSON.stringify({ ...meta, version: '4.3.2' }));
  const initial = f.snapshot();
  assert.notEqual(f.run().status, 0);
  assert.deepEqual(f.snapshot(), initial);
  fs.writeFileSync(pkgJson, JSON.stringify(meta));
  const second = path.join(f.pkg, 'dist/cjs.js');
  fs.writeFileSync(second, fs.readFileSync(second, 'utf8').replace(
    /(getKeys\(target\)\.forEach\(function\(key\) \{\n)([\t ]*)/,
    "$1$2if (key === '__proto__') throw new Error('[deepmerge] unsafe __proto__ key'); // skeleton GHSA-gcqx-w48m-w2h4\n$2",
  ));
  const mixed = f.snapshot();
  assert.notEqual(f.run().status, 0);
  assert.deepEqual(f.snapshot(), mixed);
});

test('missing distribution fails before mutating the remaining files', t => {
  const f = fixture(t);
  fs.unlinkSync(path.join(f.pkg, 'dist/umd.js'));
  const paths = files.slice(0, 2).map(rel => path.join(f.pkg, rel));
  const originals = paths.map(file => fs.readFileSync(file, 'utf8'));
  assert.notEqual(f.run().status, 0);
  assert.deepEqual(paths.map(file => fs.readFileSync(file, 'utf8')), originals);
});

test('the production verifier rejects a removed guard, an unknown version and a missing distribution', t => {
  const f = fixture(t);
  assert.equal(f.run().status, 0);
  const file = path.join(f.pkg, 'dist/cjs.js');
  const source = fs.readFileSync(file, 'utf8');
  fs.writeFileSync(file, source.replace("if (key === '__proto__') throw new Error('[deepmerge] unsafe __proto__ key'); // skeleton GHSA-gcqx-w48m-w2h4", ''));
  assert.notEqual(f.verify().status, 0);
  fs.writeFileSync(file, source);
  const pkgJson = path.join(f.pkg, 'package.json');
  const meta = JSON.parse(fs.readFileSync(pkgJson, 'utf8'));
  fs.writeFileSync(pkgJson, JSON.stringify({ ...meta, version: '4.3.2' }));
  assert.notEqual(f.verify().status, 0);
  fs.writeFileSync(pkgJson, JSON.stringify(meta));
  fs.unlinkSync(path.join(f.pkg, 'index.js'));
  assert.notEqual(f.verify().status, 0);
});

test('an Expo-nested copy fails before any reviewed package file changes', t => {
  const f = fixture(t);
  const nested = path.join(path.dirname(f.pkg), '@expo/config/node_modules/deepmerge');
  fs.mkdirSync(nested, { recursive: true });
  fs.writeFileSync(path.join(nested, 'package.json'), JSON.stringify({ name: 'deepmerge', version: '4.3.1' }));
  const originalFiles = f.snapshot();
  assert.notEqual(f.run().status, 0);
  assert.deepEqual(f.snapshot(), originalFiles);
  assert.notEqual(f.verify().status, 0);
});

test('a symlinked distribution directory fails closed before modifying its target', t => {
  const f = fixture(t);
  const dist = path.join(f.pkg, 'dist'), moved = path.join(f.pkg, 'dist-original');
  fs.renameSync(dist, moved);
  try { fs.symlinkSync(moved, dist, 'dir'); } catch (error) {
    if (error.code === 'EPERM') return t.skip('symlink privilege is unavailable');
    throw error;
  }
  const originalFiles = f.snapshot();
  assert.notEqual(f.run().status, 0);
  assert.deepEqual(f.snapshot(), originalFiles);
  assert.notEqual(f.verify().status, 0);
});

test('a symlinked package directory fails closed before modifying its target', t => {
  const f = fixture(t);
  const moved = f.pkg + '-original';
  fs.renameSync(f.pkg, moved);
  try { fs.symlinkSync(moved, f.pkg, 'dir'); } catch (error) {
    if (error.code === 'EPERM') return t.skip('symlink privilege is unavailable');
    throw error;
  }
  const originalFiles = f.snapshot();
  assert.notEqual(f.run().status, 0);
  assert.deepEqual(f.snapshot(), originalFiles);
  assert.notEqual(f.verify().status, 0);
});

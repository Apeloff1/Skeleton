'use strict';

const fs = require('node:fs');
const path = require('node:path');

function verifyDeepmergePrototypeGuard() {
  const expectedRoot = path.resolve(__dirname, '../node_modules/deepmerge');
  if (!fs.lstatSync(expectedRoot).isDirectory()) throw new Error('deepmerge package directory is unsafe');
  const metadata = path.join(expectedRoot, 'package.json');
  if (!fs.lstatSync(metadata).isFile() ||
      fs.realpathSync(require.resolve('deepmerge/package.json')) !== fs.realpathSync(metadata)) {
    throw new Error('deepmerge resolves to an unreviewed package');
  }
  const pkg = JSON.parse(fs.readFileSync(metadata, 'utf8'));
  if (pkg.version !== '4.3.1') throw new Error('deepmerge version requires security review');
  const root = expectedRoot;
  for (const dir of [root, path.join(root, 'dist')]) {
    if (!fs.lstatSync(dir).isDirectory()) throw new Error('deepmerge package directory is unsafe');
  }
  const expoMetadata = require.resolve('@expo/config/package.json');
  const expoDeepmerge = require.resolve('deepmerge/package.json', { paths: [path.dirname(expoMetadata)] });
  if (fs.realpathSync(expoDeepmerge) !== fs.realpathSync(metadata)) {
    throw new Error('Expo resolves an unreviewed deepmerge copy');
  }
  const guard = "if (key === '__proto__') throw new Error('[deepmerge] unsafe __proto__ key'); // skeleton GHSA-gcqx-w48m-w2h4";
  for (const rel of ['index.js', 'dist/cjs.js', 'dist/umd.js']) {
    const file = path.join(root, rel);
    if (!fs.lstatSync(file).isFile() || fs.statSync(file).size > 1024 * 1024) {
      throw new Error('deepmerge security target is missing or invalid');
    }
    const source = fs.readFileSync(file, 'utf8');
    for (const name of ['target', 'source']) {
      const re = new RegExp(`getKeys\\(${name}\\)\\.forEach\\(function\\(key\\) \\{\\r?\\n[\\t ]*` +
        "if \\(key === '__proto__'\\) throw new Error\\('\\[deepmerge\\] unsafe __proto__ key'\\); // skeleton GHSA-gcqx-w48m-w2h4");
      if (!re.test(source)) throw new Error('deepmerge prototype guard is missing or misplaced');
    }
    if (source.split(guard).length !== 3) throw new Error('deepmerge prototype guard has an ambiguous shape');
  }
  // Verify both public compiled variants using the installed copy. The source
  // entry's upstream-only dev dependency is not required by a production install.
  for (const rel of ['dist/cjs.js', 'dist/umd.js']) {
    const merge = require(path.join(root, rel));
    const target = JSON.parse('{"__proto__":{"polluted":"attacker"}}');
    const source = JSON.parse('{"__proto__":{"polluted":"attacker"}}');
    for (const call of [() => merge(target, {}), () => merge(Object.create(null), source)]) {
      let rejected = false;
      try { call(); } catch (error) { rejected = error instanceof Error && error.message === '[deepmerge] unsafe __proto__ key'; }
      if (!rejected) throw new Error('deepmerge accepted prototype-poisoning input');
    }
    const normal = merge({ nested: { a: 1 }, items: [1] }, { nested: { b: 2 }, items: [2] });
    if (normal.nested.a !== 1 || normal.nested.b !== 2 || normal.items.join(',') !== '1,2' || {}.polluted !== undefined) {
      throw new Error('deepmerge normal behavior or global prototype changed');
    }
  }
}

if (require.main === module) {
  verifyDeepmergePrototypeGuard();
  console.log('[verify-deepmerge-security] prototype guard verified');
}
module.exports = { verifyDeepmergePrototypeGuard };

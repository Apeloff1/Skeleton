'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

const source = fs.readFileSync(
  path.resolve(__dirname, '..', 'src/utils/quickWins2.ts'), 'utf8',
);
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
  },
});
const sandbox = { exports: {} };
vm.runInNewContext(compiled.outputText, sandbox, { timeout: 5000 });
const utils = sandbox.exports;

test('unsafe object paths cannot access inherited prototype graph', () => {
  const fallback = Symbol('invalid path');
  const data = { nested: { safe: 1 } };
  assert.equal(utils.get(data, 'nested.safe', fallback), 1);
  for (const path of ['__proto__.polluted', 'constructor.prototype.admin', 'prototype']) {
    assert.equal(utils.get(data, path, fallback), fallback);
    assert.throws(() => utils.set(data, path, true), /unsafe object path/);
  }
  assert.equal(Object.prototype.polluted, undefined);
  assert.equal(utils.set(data, 'nested.safe', 2).nested.safe, 2);
  assert.equal(data.nested.safe, 1);
});

test('deepMerge never assigns attacker-controlled prototype keys', () => {
  const payload = JSON.parse(
    '{"__proto__":{"isAdmin":true},"constructor":{"prototype":{"isAdmin":true}},"safe":{"ok":true}}',
  );
  const merged = utils.deepMerge(payload, { safe: { valid: true } });
  assert.equal(merged.safe.ok, true);
  assert.equal(merged.safe.valid, true);
  assert.equal(Object.prototype.isAdmin, undefined);
  assert.equal(Object.hasOwn(merged, '__proto__'), false);
  assert.equal(Object.hasOwn(merged, 'constructor'), false);
});

test('dictionary helpers store hostile keys without changing their prototype', () => {
  const source = JSON.parse('{"__proto__":"input","constructor":"value","safe":"ok"}');
  for (const result of [
    utils.mapValues(source, value => value),
    utils.filterObject(source, () => true),
    utils.invert(source),
    utils.groupBy(['__proto__', 'constructor', 'safe'], value => value),
  ]) {
    assert.equal(Object.getPrototypeOf(result), null);
    assert.equal(Object.prototype.polluted, undefined);
  }
  assert.equal(utils.groupBy(['__proto__'], x => x)['__proto__'][0], '__proto__');
});

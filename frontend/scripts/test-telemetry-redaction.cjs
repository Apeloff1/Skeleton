'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'src/utils/securityTelemetry.ts'), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const context = vm.createContext({ exports: {} });
vm.runInContext(compiled, context, { timeout: 5000 });
const scrub = context.exports.scrubTelemetry;

test('sensitive key names and nested URL/header tokens are redacted', () => {
  const payload = vm.runInContext(`({
    session: {
      authorization: 'Bearer SPECIAL_AUTH_TOKEN',
      cookie: 'session=SECRET',
      api_key: 'PRIVATE_API_KEY',
      url: 'https://example.test/api?token=VERY_PRIVATE&debug=1',
    },
    error: 'Authorization: Bearer TOPSECRET password=hunter2',
    normal: 'safe telemetry',
  })`, context);
  const result = scrub(payload);
  assert.equal(result.session.authorization, '[REDACTED]');
  assert.equal(result.session.cookie, '[REDACTED]');
  assert.equal(result.session.api_key, '[REDACTED]');
  assert.ok(!JSON.stringify(result).includes('SPECIAL_AUTH_TOKEN'));
  assert.ok(!JSON.stringify(result).includes('PRIVATE_API_KEY'));
  assert.ok(!JSON.stringify(result).includes('VERY_PRIVATE'));
  assert.ok(!JSON.stringify(result).includes('TOPSECRET'));
  assert.ok(!JSON.stringify(result).includes('hunter2'));
  assert.equal(result.normal, 'safe telemetry');
});

test('getter traps, prototype keys, and inherited details cannot be serialized', () => {
  const value = vm.runInContext(`(() => {
    const item = Object.create(null);
    Object.defineProperty(item, 'password', { value: 'SECRET', enumerable: true });
    Object.defineProperty(item, 'danger', {
      enumerable: true, get() { throw new Error('GETTER_CALLED'); },
    });
    item['__proto__'] = { leaked: true };
    return item;
  })()`, context);
  const result = scrub(value);
  assert.equal(result.password, '[REDACTED]');
  assert.equal(result.danger, '[UNSUPPORTED]');
  assert.equal(Object.prototype.hasOwnProperty.call(result, '__proto__'), false);
  assert.ok(!JSON.stringify(result).includes('GETTER_CALLED'));
});

test('cycles, depth, collection size, and strings remain bounded', () => {
  const value = vm.runInContext(`(() => {
    const top = { text: 'a'.repeat(20000), numbers: Array.from({ length: 2000 }, (_, i) => i) };
    top.self = top;
    top.deep = { a: { b: { c: { d: { e: { f: 'secret' } } } } } };
    return top;
  })()`, context);
  const result = scrub(value);
  assert.equal(result.text.length, 1024);
  assert.equal(result.numbers.length, 80);
  assert.equal(result.self, '[CIRCULAR]');
  assert.equal(result.deep.a.b.c.d, '[TRUNCATED]');
});

test('host objects and non-finite numbers fail closed', () => {
  assert.equal(scrub(new Error('secret')), '[UNSUPPORTED]');
  assert.equal(scrub(Number.POSITIVE_INFINITY), null);
  assert.equal(scrub(undefined), null);
});

test('offline flush sanitizes legacy queue and retains failed in-flight batches', () => {
  const source = fs.readFileSync(path.join(root, 'src/utils/modalLogger.ts'), 'utf8');
  assert.match(source, /let safeBatch: TelemetryEvent\[\] = \[\]/);
  assert.match(source, /safeBatch = scrubTelemetry\(batch\)/);
  assert.match(source, /if \(safeBatch\.length\) await _persistQueue\(safeBatch\)/);
  assert.doesNotMatch(source, /stack: err\.stack|console\.warn\([^\n]*detail\)/);
});

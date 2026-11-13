'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(
  path.join(root, 'src/features/WasmCompiler/WasmCompiler.ts'), 'utf8',
);
const output = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;

function compilerFixture() {
  const calls = [];
  const sandbox = vm.createContext({
    exports: {},
    require(name) {
      if (name === 'react-native') return { Platform: { OS: 'web' } };
      throw new Error('disallowed external module');
    },
    performance: { now: () => Date.now() },
    console: { log() {}, warn() {}, error() {} },
    setTimeout,
    clearTimeout,
    Date,
    window: {},
  });
  vm.runInContext(output, sandbox, { timeout: 5000 });
  sandbox.__ALLOW_UNSAFE_CODE_EXECUTION__ = true;
  const instance = new sandbox.exports.WasmCompiler();

  const handles = {
    log: { dispose() { calls.push('dispose:log'); } },
    console: { dispose() { calls.push('dispose:console'); } },
  };
  instance.quickJS = {
    newRuntime() {
      calls.push('newRuntime');
      return {
        setMemoryLimit(value) { calls.push(['memory', value]); },
        setMaxStackSize(value) { calls.push(['stack', value]); },
        setInterruptHandler(fn) {
          assert.equal(typeof fn, 'function');
          calls.push('interrupt');
        },
        newContext() {
          return {
            global: {},
            undefined: undefined,
            newObject() { return handles.console; },
            newFunction(name, callback) {
              assert.equal(name, 'log');
              callback('safe_guest_log');
              return handles.log;
            },
            dump(handle) { return handle; },
            setProp(target, prop) { calls.push(['guestProp', prop]); },
            evalCode(code, filename) {
              calls.push(['evalGuest', code, filename]);
              return { value: { dispose() { calls.push('dispose:value'); } } };
            },
            dispose() { calls.push('dispose:guest'); },
          };
        },
        dispose() { calls.push('dispose:runtime'); },
      };
    },
  };
  return { instance, calls, sandbox };
}

test('never construct browser-native Function from caller source', () => {
  const begin = source.indexOf('private async compileJavaScript(');
  const end = source.indexOf('C/C++ COMPILATION', begin);
  assert.ok(begin >= 0 && end > begin);
  const section = source.slice(begin, end);
  assert.doesNotMatch(section, /FunctionCtor|new Function|eval\(/);
  assert.match(section, /this\.quickJS\.newRuntime\(\)/);
  assert.match(section, /setMemoryLimit\(/);
  assert.match(section, /setMaxStackSize\(/);
  assert.match(section, /setInterruptHandler\(/);
});

test('isolated guest consumes source and releases handles without native execution', async () => {
  const { instance, calls, sandbox } = compilerFixture();
  sandbox.Function = () => { throw new Error('native Function must not execute'); };
  const result = await instance.compile('console.log("hello")', 'javascript');
  assert.equal(result.success, true);
  assert.ok(calls.find(call => Array.isArray(call) && call[0] === 'memory' && call[1] <= 32 * 1024 * 1024));
  assert.ok(calls.find(call => Array.isArray(call) && call[0] === 'stack' && call[1] <= 256 * 1024));
  assert.ok(calls.find(call => Array.isArray(call) && call[0] === 'evalGuest' && call[1] === 'console.log("hello")'));
  for (const kind of ['dispose:value', 'dispose:log', 'dispose:console', 'dispose:guest', 'dispose:runtime']) {
    assert.ok(calls.includes(kind), kind);
  }
});

test('oversized sources and missing QuickJS sandbox fail closed', async () => {
  const { instance, calls } = compilerFixture();
  const oversized = await instance.compile('x'.repeat(65537), 'javascript');
  assert.equal(oversized.success, false);
  assert.equal(calls.includes('newRuntime'), false);
  instance.quickJS = null;
  instance.loadQuickJS = async () => {};
  const missing = await instance.compile('console.log("hello")', 'javascript');
  assert.equal(missing.success, false);
  assert.equal(calls.includes('newRuntime'), false);
});

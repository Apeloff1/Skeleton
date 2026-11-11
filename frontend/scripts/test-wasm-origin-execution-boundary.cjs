'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

const source = fs.readFileSync(
  path.join(__dirname, '..', 'src/features/WasmCompiler/WasmCompiler.ts'),
  'utf8',
);
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
    esModuleInterop: true,
  },
});
assert.equal(compiled.diagnostics?.filter(x => x.category === ts.DiagnosticCategory.Error).length || 0, 0);
const sandbox = vm.createContext({
  exports: {},
  performance: { now: () => 123 },
  localStorage: { getItem: () => 'true' },
  __ALLOW_UNSAFE_CODE_EXECUTION__: true,
});
vm.runInContext(compiled.outputText, sandbox, { timeout: 5000 });
const { WasmCompiler, wasmCompiler } = sandbox.exports;

test('untrusted source cannot execute in the application origin even after user-controlled opt-in', async () => {
  const samples = [
    ['javascript', 'globalThis.compromised = true'],
    ['python', "import js; js.window.compromised = True"],
    ['c', 'int main() { return 1; }'],
    ['cpp', 'int main() { return 1; }'],
    ['rust', 'fn main() {}'],
  ];
  const app = new WasmCompiler();
  await app.initialize();
  for (const [language, sourceCode] of samples) {
    const result = await app.compile(sourceCode, language);
    assert.equal(result.success, false, language);
    assert.equal(result.errors[0].type, 'fatal');
    assert.match(result.errors[0].message, /Isolated compiler runtime unavailable/);
    assert.equal(result.metrics.codegenTime, 0);
    assert.equal(result.stages[0].status, 'error');
    assert.equal(result.wasm, undefined);
    assert.equal(result.assembly, undefined);
    assert.equal(result.ir, undefined);
  }
  assert.equal(sandbox.compromised, undefined);
  assert.deepEqual(JSON.parse(JSON.stringify(app.getStatus())), {
    python: false, javascript: false, cpp: false,
  });
});

test('long untrusted source is rejected before parsing or attempted execution', async () => {
  const app = new WasmCompiler();
  const result = await app.compile('x'.repeat(200_001), 'javascript');
  assert.equal(result.success, false);
  assert.match(result.errors[0].message, /bounded string/);
  const nullResult = await app.compile(null, 'python');
  assert.equal(nullResult.success, false);
  const unknown = await app.compile('safe', 'unregistered');
  assert.equal(unknown.success, false);
  assert.match(unknown.errors[0].message, /Unsupported language/);
});

test('legacy execute string API reports a hold rather than executing source', async () => {
  const response = await wasmCompiler.execute(
    'globalThis.compromised = true', 'javascript',
  );
  assert.match(response, /Isolated compiler runtime unavailable/);
  assert.equal(sandbox.compromised, undefined);
});

test('browser execution, dynamic loader and user-configured gate cannot reappear', () => {
  const prohibited = [
    /\bnew\s+(?:Function|FunctionCtor)\s*\(/,
    /\b(?:eval|Function)\s*\(/,
    /\.runPythonAsync\s*\(/,
    /import\s*\(\s*['"]https?:\/\//,
    /\bloadScript\s*\(/,
    /\bcreateElement\s*\(\s*['"]script['"]/,
    /\b__ALLOW_UNSAFE_CODE_EXECUTION__\b/,
    /\bALLOW_UNSAFE_CODE_EXECUTION\b/,
  ];
  // Source comments may mention user flag concept but must never contain
  // the literal old flag name or execution primitive.
  for (const regex of prohibited) {
    assert.doesNotMatch(source, regex, regex.toString());
  }
});

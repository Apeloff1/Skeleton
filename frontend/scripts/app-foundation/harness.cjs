'use strict';
/* global __dirname */
// Transpile a dependency-light foundation module with TypeScript only (no Babel,
// no node_modules beyond `typescript`) so CI can run it via NODE_PATH.
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const ROOT = path.resolve(__dirname, '..', '..');

function load(rel, mocks = {}) {
  const src = fs.readFileSync(path.join(ROOT, rel), 'utf8');
  const out = ts.transpileModule(src, {
    fileName: rel,
    compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS, esModuleInterop: true },
    reportDiagnostics: true,
  });
  if ((out.diagnostics || []).length) throw new Error(rel + ': transpile diagnostics');
  const mod = { exports: {} };
  new Function('require', 'module', 'exports', out.outputText)((name) => {
    if (Object.prototype.hasOwnProperty.call(mocks, name)) return mocks[name];
    throw new Error(`${rel}: unexpected import ${name}`);
  }, mod, mod.exports);
  return mod.exports;
}

module.exports = { load, ROOT };

'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

const root = path.resolve(__dirname, '..');
const moduleSource = fs.readFileSync(path.join(root, 'src/utils/telemetryPrivacy.ts'), 'utf8');
const compiled = ts.transpileModule(moduleSource, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
  },
});
const context = vm.createContext({ exports: {} });
vm.runInContext(compiled.outputText, context, { timeout: 5000 });
const privacy = context.exports;

test('labels and events accept only bounded structural identifiers', () => {
  assert.equal(privacy.safeTelemetryLabel('GalaxyStudioFactoryModal'), 'GalaxyStudioFactoryModal');
  assert.equal(privacy.safeTelemetryLabel('https://example.test/?token=secret'), 'unknown');
  assert.equal(privacy.safeTelemetryEvent('action:packageBuild_clicked'), 'action:packageBuild_clicked');
  assert.equal(privacy.safeTelemetryEvent('Bearer private'), 'other');
  assert.equal(privacy.safeTelemetryEvent('action:' + 'x'.repeat(100)), 'other');
});

test('details discard sensitive keys and arbitrary string values', () => {
  const detail = vm.runInContext(
    '({authorization:"Bearer private", safe:{url:"https://x.test/?api_key=private"}, tokens:[{access_token:"private"}], user:"private", status:"success", count:3, enabled:true})',
    context,
  );
  const safe = privacy.sanitizeTelemetryDetail(detail);
  assert.equal(JSON.stringify(safe).includes('private'), false);
  assert.equal(safe.authorization, undefined);
  assert.equal(safe.safe, undefined);
  assert.equal(safe.user, undefined);
  assert.equal(safe.status, 'success');
  assert.equal(safe.count, 3);
  assert.equal(safe.enabled, true);
});

test('hostile accessors are never invoked', () => {
  context.accessorReads = 0;
  const hostile = vm.runInContext(
    'Object.defineProperties({}, { token: { enumerable: true, get() { accessorReads++; return "secret"; } }, status: { enumerable: true, get() { accessorReads++; return "success"; } } })',
    context,
  );
  assert.equal(privacy.sanitizeTelemetryDetail(hostile), undefined);
  assert.equal(context.accessorReads, 0);
});

test('nested, circular and unsupported values are rejected without recursion', () => {
  const circular = vm.runInContext('(() => { const value={}; value.self=value; return value; })()', context);
  assert.equal(privacy.sanitizeTelemetryDetail(circular), undefined);
  assert.equal(privacy.sanitizeTelemetryDetail(vm.runInContext('new Date()', context)), undefined);
  assert.equal(privacy.sanitizeTelemetryDetail(vm.runInContext('({status:"Bearer private"})', context)), undefined);
});

test('hostile proxy reflection fails closed', () => {
  const hostile = vm.runInContext(
    'new Proxy({}, {ownKeys() { throw new Error("private trap"); }})',
    context,
  );
  assert.equal(privacy.sanitizeTelemetryDetail(hostile), undefined);
});

test('untrusted error objects cannot disclose message or execute getters', () => {
  context.accessorReads = 0;
  const hostile = vm.runInContext(
    'Object.defineProperties({}, { name: { get() { accessorReads++; return "TypeError"; } }, message: { get() { accessorReads++; return "private"; } } })',
    context,
  );
  assert.equal(privacy.safeTelemetryErrorType(hostile), 'Error');
  assert.equal(context.accessorReads, 0);
  assert.equal(privacy.safeTelemetryErrorType(vm.runInContext('({name:"TypeError"})', context)), 'TypeError');
});

test('modal logger sanitizes restored events and outbound diagnostics', () => {
  const logger = fs.readFileSync(path.join(root, 'src/utils/modalLogger.ts'), 'utf8');
  assert.doesNotMatch(logger, /err\.message|err\.stack|String\(err\)/);
  assert.match(logger, /sanitizeQueuedEvent/);
  assert.match(logger, /sanitizeTelemetryDetail/);
  assert.match(logger, /safeTelemetryErrorType/);
  assert.match(logger, /pending\.slice\(0, 100\)/);
  assert.doesNotMatch(logger, /console\.warn\([^\n]*detail/);
});

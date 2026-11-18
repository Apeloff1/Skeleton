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

test('client text never forwards bearer credentials or URL secrets', () => {
  const variants = [
    'Authorization: Bearer super-secret-token',
    'https://api.example.test/resource?token=super-secret-token&valid=true',
    'api_key=super-secret-token',
    'Password: super-secret-token',
    'Bearer super-secret-token',
  ];
  for (const input of variants) {
    const result = privacy.redactTelemetryText(input);
    assert.equal(result.includes('super-secret-token'), false, input);
    assert.equal(result.length <= 512, true);
  }
  assert.equal(privacy.redactTelemetryText('safe_event'), 'safe_event');
});

test('telemetry detail admits only bounded safe scalar fields', () => {
  const detail = vm.runInContext(
    '({authorization:"Bearer private", safe:{url:"https://x.test/?api_key=private"}, tokens:[{access_token:"private"}], user:"ok", status:"success", duration:42, enabled:true})',
    context,
  );
  const safe = privacy.sanitizeTelemetryDetail(detail);
  assert.equal(JSON.stringify(safe).includes('private'), false);
  assert.equal(safe.status, 'success');
  assert.equal(safe.duration, 42);
  assert.equal(safe.enabled, true);
  assert.equal(Object.hasOwn(safe, 'authorization'), false);
  assert.equal(Object.hasOwn(safe, 'safe'), false);
});

test('untrusted getters are never invoked during detail sanitization', () => {
  context.accessorReads = 0;
  const hostile = vm.runInContext(
    'Object.defineProperties({}, { token: { enumerable: true, get() { accessorReads++; return "secret"; } }, status: { enumerable: true, get() { accessorReads++; return "success"; } } })',
    context,
  );
  const sanitized = privacy.sanitizeTelemetryDetail(hostile);
  assert.equal(context.accessorReads, 0);
  assert.equal(sanitized, undefined);
});

test('unsupported, circular and excessive telemetry values fail closed', () => {
  const circular = vm.runInContext('(() => { const value={}; value.self=value; return value; })()', context);
  assert.equal(privacy.sanitizeTelemetryDetail(circular), undefined);
  assert.equal(privacy.sanitizeTelemetryDetail(vm.runInContext('new Date()', context)), undefined);
  assert.equal(privacy.safeTelemetryLabel('a'.repeat(2_000)), 'unknown');
  assert.equal(privacy.safeTelemetryEvent('Bearer super-secret-token'), 'other');
});

test('hostile proxy reflection fails closed without leaking values', () => {
  const hostile = vm.runInContext(
    'new Proxy({}, {ownKeys() { throw new Error("private trap"); }})',
    context,
  );
  assert.equal(privacy.sanitizeTelemetryDetail(hostile), undefined);
});

test('persisted event fields are constrained by the current privacy contract', () => {
  assert.equal(privacy.safeTelemetryLabel('safe_modal'), 'safe_modal');
  assert.equal(privacy.safeTelemetryLabel('https://host/?token=private'), 'unknown');
  assert.equal(privacy.safeTelemetryEvent('error'), 'error');
  assert.equal(privacy.safeTelemetryEvent('action:clicked'), 'action:clicked');
  assert.equal(privacy.safeTelemetryEvent('Bearer private'), 'other');
  assert.equal(privacy.safeTelemetryErrorType(vm.runInContext('({name:"CustomSecretError"})', context)), 'Error');
});

test('modal logger does not transmit raw exception text or stack', () => {
  const logger = fs.readFileSync(path.join(root, 'src/utils/modalLogger.ts'), 'utf8');
  assert.doesNotMatch(logger, /err\.message|err\.stack|String\(err\)/);
  assert.match(logger, /sanitizeQueuedEvent/);
  assert.match(logger, /safeTelemetryEvent/);
  assert.match(logger, /safeTelemetryLabel/);
  assert.match(logger, /sanitizeTelemetryDetail/);
  assert.doesNotMatch(logger, /console\.warn\([^\n]*detail/);
});

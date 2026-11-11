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

test('nested sensitive fields are replaced rather than serialized', () => {
  const detail = vm.runInContext(
    '({authorization:"Bearer private", safe:{url:"https://x.test/?api_key=private"}, tokens:[{access_token:"private"}], user:"ok"})',
    context,
  );
  const safe = privacy.sanitizeTelemetryDetail(detail);
  const serialized = JSON.stringify(safe);
  assert.equal(serialized.includes('private'), false);
  assert.equal(safe.authorization, '[REDACTED]');
  assert.equal(safe.safe.url.includes('[REDACTED]'), true);
  assert.equal(safe.user, 'ok');
});

test('secret accessors are never evaluated during redaction', () => {
  context.accessorReads = 0;
  const hostile = vm.runInContext(
    'Object.defineProperties({}, { token: { enumerable: true, get() { accessorReads++; return "secret"; } }, safe: { enumerable: true, get() { accessorReads++; return "also-secret"; } } })',
    context,
  );
  const sanitized = privacy.sanitizeTelemetryDetail(hostile);
  assert.equal(context.accessorReads, 0);
  assert.equal(sanitized.token, '[REDACTED]');
  assert.equal(sanitized.safe, '[ACCESSOR_REDACTED]');
});

test('circular objects, deep payloads and unsupported values are bounded', () => {
  const circular = vm.runInContext('(() => { const value={}; value.self=value; return value; })()', context);
  assert.equal(privacy.sanitizeTelemetryDetail(circular).self, '[CIRCULAR]');
  const deep = vm.runInContext('({ a: { b: { c: { d: { text:"private" } } } } })', context);
  assert.equal(JSON.stringify(privacy.sanitizeTelemetryDetail(deep)).includes('private'), false);
  assert.equal(privacy.redactTelemetryText('a'.repeat(2_000)).length, 512);
  assert.equal(privacy.sanitizeTelemetryDetail(vm.runInContext('new Date()', context)), '[UNSUPPORTED]');
});

test('tampered persisted events are admitted only after sanitization', () => {
  const event = vm.runInContext(
    '({modal_id:"safe_modal",session_id:"s_secure",event:"error",severity:"fatal",detail:{token:"private",message:"Bearer private"},duration_ms:300})',
    context,
  );
  const result = privacy.sanitizeTelemetryEvent(event);
  assert.equal(result.modal_id, 'safe_modal');
  assert.equal(result.severity, 'fatal');
  assert.equal(JSON.stringify(result).includes('private'), false);
  assert.equal(privacy.sanitizeTelemetryEvent(vm.runInContext('({session_id:"only"})', context)), null);
});

test('modal logger does not transmit raw exception text or stack', () => {
  const logger = fs.readFileSync(path.join(root, 'src/utils/modalLogger.ts'), 'utf8');
  assert.doesNotMatch(logger, /err\.message|err\.stack|String\(err\)/);
  assert.match(logger, /sanitizeTelemetryEvent/);
  assert.match(logger, /sanitizeTelemetryDetail/);
  assert.doesNotMatch(logger, /console\.warn\([^\n]*detail/);
});

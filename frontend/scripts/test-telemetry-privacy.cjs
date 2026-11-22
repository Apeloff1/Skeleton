'use strict';

// Regression contract for the current allowlist-only telemetry API.
// Do not restore the legacy free-text redaction interface: it permitted
// attacker-controlled strings into the offline telemetry transport.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'src/utils/telemetryPrivacy.ts'), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  reportDiagnostics: true,
});
assert.equal(compiled.diagnostics?.length ?? 0, 0);
const context = vm.createContext({ exports: {} });
vm.runInContext(compiled.outputText, context, { timeout: 5000 });
const privacy = context.exports;

test('event names and labels reject credentials, URLs and arbitrary text', () => {
  for (const value of [
    'Authorization: Bearer super-secret-token',
    'https://api.example.test/?token=super-secret-token',
    'api_key=super-secret-token',
    'Bearer super-secret-token',
    'https://api.example.test/private',
    'Authorization:Bearer',
    'bearer:private',
    'token:private',
    'session:private',
    'api_key:private',
    'password:private',
    'secret.private',
  ]) {
    assert.equal(privacy.safeTelemetryLabel(value), 'unknown');
    assert.equal(privacy.safeTelemetryEvent(value), 'other');
  }
  assert.equal(privacy.safeTelemetryLabel('safe_event'), 'safe_event');
  assert.equal(privacy.safeTelemetryEvent('action:build'), 'action:build');
  assert.equal(privacy.safeTelemetryEvent('action:build?token=secret'), 'other');
});

test('nested fields and credentials are dropped, never serialized', () => {
  const detail = vm.runInContext(
    '({authorization:"Bearer private", safe:{url:"https://x.test/?api_key=private"}, tokens:[{access_token:"private"}], user:"ok", status:"failed", count:3})',
    context,
  );
  const safe = privacy.sanitizeTelemetryDetail(detail);
  assert.equal(safe.status, 'failed');
  assert.equal(safe.count, 3);
  assert.equal(JSON.stringify(safe).includes('private'), false);
  assert.equal(Object.hasOwn(safe, 'authorization'), false);
  assert.equal(Object.hasOwn(safe, 'safe'), false);
  assert.equal(Object.hasOwn(safe, 'user'), false);
});

test('accessors are not invoked and sensitive keys are dropped', () => {
  context.accessorReads = 0;
  const hostile = vm.runInContext(
    'Object.defineProperties({ count: 4 }, { token: { enumerable: true, get() { accessorReads++; return "secret"; } }, status: { enumerable: true, get() { accessorReads++; return "failed"; } } })',
    context,
  );
  const safe = privacy.sanitizeTelemetryDetail(hostile);
  assert.equal(context.accessorReads, 0);
  assert.equal(safe.count, 4);
  assert.equal(Object.hasOwn(safe, 'token'), false);
  assert.equal(Object.hasOwn(safe, 'status'), false);
});

test('cycles, deep payloads, arrays and unsupported values are dropped', () => {
  const circular = vm.runInContext('(() => { const value={}; value.self=value; return value; })()', context);
  assert.equal(privacy.sanitizeTelemetryDetail(circular), undefined);
  const deep = vm.runInContext('({ a: { b: { c: { d: { text:"private" } } } } })', context);
  assert.equal(privacy.sanitizeTelemetryDetail(deep), undefined);
  assert.equal(privacy.sanitizeTelemetryDetail(vm.runInContext('new Date()', context)), undefined);
  assert.equal(privacy.sanitizeTelemetryDetail([]), undefined);
});

test('hostile proxy reflection fails closed without leaking', () => {
  const hostile = vm.runInContext(
    'new Proxy({}, { ownKeys() { throw new Error("private trap"); } })', context,
  );
  assert.equal(privacy.sanitizeTelemetryDetail(hostile), undefined);
});

test('numeric, boolean and categorical values are bounded', () => {
  const result = privacy.sanitizeTelemetryDetail({
    status: 'FAILED', count: 5, ready: true, bad: Infinity,
    huge: 1e12, message: 'private', mode: 'arbitrary free text',
  });
  assert.equal(result.status, 'failed');
  assert.equal(result.count, 5);
  assert.equal(result.ready, true);
  assert.equal(Object.hasOwn(result, 'bad'), false);
  assert.equal(Object.hasOwn(result, 'huge'), false);
  assert.equal(Object.hasOwn(result, 'message'), false);
  assert.equal(Object.hasOwn(result, 'mode'), false);
});

test('modal logger sanitizes before persistence and transport', () => {
  const logger = fs.readFileSync(path.join(root, 'src/utils/modalLogger.ts'), 'utf8');
  assert.doesNotMatch(logger, /err\.message|err\.stack|String\(err\)/);
  assert.match(logger, /sanitizeTelemetryDetail/);
  assert.match(logger, /sanitizeQueuedEvent/);
  assert.match(logger, /\.map\(sanitizeQueuedEvent\)/);
  assert.match(logger, /detail: sanitizeTelemetryDetail\(row\.detail\)/);
  assert.doesNotMatch(logger, /console\.warn\([^\n]*detail/);
});

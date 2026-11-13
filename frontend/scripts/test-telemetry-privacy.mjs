import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

const privacySource = await readFile(
  new URL('../src/utils/telemetryPrivacy.ts', import.meta.url), 'utf8',
);
const compiled = ts.transpileModule(privacySource, {
  compilerOptions: {
    target: ts.ScriptTarget.ES2022,
    module: ts.ModuleKind.ES2022,
    strict: true,
  },
  fileName: 'telemetryPrivacy.ts',
  reportDiagnostics: true,
});
assert.equal((compiled.diagnostics ?? []).length, 0,
  (compiled.diagnostics ?? []).map(d =>
    ts.flattenDiagnosticMessageText(d.messageText, '\n')).join('\n'));
const {
  safeTelemetryLabel, safeTelemetryEvent, safeTelemetryErrorType,
  sanitizeTelemetryDetail,
} = await import('data:text/javascript;base64,' +
  Buffer.from(compiled.outputText).toString('base64'));

const legacySource = await readFile(
  new URL('../src/utils/modalLogger.ts', import.meta.url), 'utf8',
);

test('captures only bounded categorical/numeric telemetry, not secrets or free text', () => {
  const unsafe = {
    status: 'FAILED',
    state: 'running',
    count: 5,
    duration: 3.5,
    ready: false,
    password: 'password=supersecret',
    authorization: 'Bearer secret_token',
    stack: '/home/user/private/source.ts',
    message: 'private account data',
    content: 'private prompt',
    query: 'api_key=secret',
    url: 'https://user:pass@private.invalid',
    cardNumber: 123456789,
    path: 'C:\\Users\\Private',
    freeform: 'untrusted developer input',
    payload: { nested: 'token' },
    malformed: Number.POSITIVE_INFINITY,
    overbudget: 1e12,
  };
  const result = sanitizeTelemetryDetail(unsafe);
  assert.equal(JSON.stringify(result),
    JSON.stringify({ status: 'failed', state: 'running',
      count: 5, duration: 3.5, ready: false }));
  const serialized = JSON.stringify(result);
  for (const token of ['supersecret', 'Bearer', 'private.invalid', 'private prompt',
    'private account', 'C:\\Users', '123456789']) {
    assert.ok(!serialized.includes(token), token);
  }
});

test('rejects getters, proxies, arrays, cycles and dynamic exception text', () => {
  let getterCalls = 0;
  const untrusted = {
    count: 4,
    get token() {
      getterCalls += 1;
      return 'private-secret';
    },
  };
  assert.equal(sanitizeTelemetryDetail(untrusted).count, 4);
  assert.equal(getterCalls, 0);
  const cycle = {};
  cycle.nested = cycle;
  assert.equal(sanitizeTelemetryDetail(cycle), undefined);
  assert.equal(sanitizeTelemetryDetail([]), undefined);
  const maliciousProxy = new Proxy({}, {
    ownKeys() { throw new Error('password=private'); },
  });
  assert.equal(sanitizeTelemetryDetail(maliciousProxy), undefined);
  const err = new Error('password=not-for-telemetry');
  err.stack = 'Bearer secret in stack';
  assert.equal(safeTelemetryErrorType(err), 'Error');
  assert.ok(!JSON.stringify(sanitizeTelemetryDetail(err)).includes('password'));
});

test('untrusted labels and event names never contain arbitrary URLs or queries', () => {
  assert.equal(safeTelemetryLabel('GalaxyStudio'), 'GalaxyStudio');
  assert.equal(safeTelemetryLabel('Bearer secret'), 'unknown');
  assert.equal(safeTelemetryLabel('https://example.invalid?token=x'), 'unknown');
  assert.equal(safeTelemetryEvent('action:build'), 'action:build');
  assert.equal(safeTelemetryEvent('action:build?session_key=secret'), 'other');
  assert.equal(safeTelemetryEvent('error'), 'error');
});

test('offline queue is sanitized before persistence, after restore and before POST', () => {
  // React Native module cannot be run in a Node environment, but this test
  // checks the transport/storage boundary in the actual source, and the
  // behavioral sanitization is tested independently above.
  assert.match(legacySource, /\.map\(sanitizeQueuedEvent\)/);
  assert.match(legacySource, /detail: sanitizeTelemetryDetail\(row\.detail\)/);
  assert.match(legacySource, /detail: sanitizeTelemetryDetail\(detail\)/);
  assert.match(legacySource, /await AsyncStorage\.removeItem\(QUEUE_KEY\)/);
  assert.match(legacySource, /const part = pending\.slice\(0, 200\)/);
  assert.match(legacySource, /_flushInflight = true/);
  assert.doesNotMatch(legacySource, /stack:\s*err\.stack/);
  assert.doesNotMatch(legacySource, /message:\s*err\.message/);
  assert.doesNotMatch(legacySource, /console\.warn\([^\n]*\bdetail\b/);
});

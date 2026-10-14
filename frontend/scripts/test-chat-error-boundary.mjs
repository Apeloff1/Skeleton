import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

// Load the actual browser-side TypeScript without importing the Expo runtime.
const source = await readFile(new URL('../src/product/chatErrors.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022, strict: true },
  fileName: 'chatErrors.ts',
  reportDiagnostics: true,
});
assert.equal((compiled.diagnostics ?? []).length, 0,
  (compiled.diagnostics ?? []).map(d => ts.flattenDiagnosticMessageText(d.messageText, '\n')).join('\n'));
const { ChatClientError, chatApiError, asChatError, chatAbortError } = await import(
  'data:text/javascript;base64,' + Buffer.from(compiled.outputText).toString('base64')
);

function response(status, detail, error = null, rid = 'trace-safe-1') {
  return { ok: false, status, data: detail, error, rid };
}

test('authorized validation details retain typed error, stable code and correlation', () => {
  const err = chatApiError(response(400, { detail: { message: 'Input rejected', code: 'invalid_input' } }), 'Fallback');
  assert.ok(err instanceof ChatClientError);
  assert.equal(err.kind, 'validation');
  assert.equal(err.code, 'invalid_input');
  assert.equal(err.requestId, 'trace-safe-1');
  assert.equal(err.retryable, false);
  assert.equal(err.message, 'Input rejected');
});

test('conflict and permission failures never become retryable', () => {
  assert.equal(chatApiError(response(409, { detail: 'Version moved' }), 'Conflict').kind, 'conflict');
  const denied = chatApiError(response(403, { detail: 'Unauthorized' }), 'Denied');
  assert.equal(denied.kind, 'authorization');
  assert.equal(denied.retryable, false);
});

test('server faults and throttling hide remote internals but preserve request IDs', () => {
  const msg = 'postgresql://secret-user:password@internal.example/private';
  for (const status of [429, 500, 503]) {
    const err = chatApiError(response(status, { detail: { message: msg, code: 'server_failure' } }, msg), 'The service is temporarily unavailable.');
    assert.equal(err.kind, 'unavailable');
    assert.equal(err.message, 'The service is temporarily unavailable.');
    assert.equal(err.code, 'server_failure');
    assert.equal(err.requestId, 'trace-safe-1');
    assert.equal(err.retryable, true);
  }
});

test('network exception messages never expose sensitive transport internals', () => {
  const err = asChatError(new Error('password=not-for-ui'), 'Connection failed.');
  assert.equal(err.kind, 'network');
  assert.equal(err.message, 'Connection failed.');
  assert.equal(err.retryable, true);
  const responseError = chatApiError(response(0, null, 'api_key=not-for-ui'), 'Connection failed.');
  assert.equal(responseError.message, 'Connection failed.');
});

test('aborts stay cancelled and never retry; typed errors remain unchanged', () => {
  const abort = chatAbortError();
  assert.equal(abort.kind, 'cancelled');
  assert.equal(abort.retryable, false);
  assert.equal(asChatError(abort), abort);
  const thrown = new Error('The operation was aborted');
  thrown.name = 'AbortError';
  assert.equal(asChatError(thrown).kind, 'cancelled');
});

test('untrusted error codes and excessively long correlation values are bounded', () => {
  const err = chatApiError(response(422, {
    detail: { message: 'Invalid', code: '<script>' },
  }, null, 'x'.repeat(400)), 'Invalid data');
  assert.equal(err.code, 'validation');
  assert.equal(err.requestId, null);
});

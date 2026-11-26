'use strict';
// Load-failure mapping + inline loading/error notices. Run: yarn test:app-foundation:render
const test = require('node:test');
const assert = require('node:assert/strict');
const { h, load, render, text, attrs } = require('../../skeleton-forge/harness.cjs');

const lf = load('src/foundation/loadFailure.ts');
const { LoadingNotice, LoadErrorNotice } = load('src/foundation/LoadNotice.tsx');

test('classifies transport outcomes into honest kinds', () => {
  const k = (input) => lf.classifyFailure(input);
  assert.equal(k({ status: 401 }), 'unauthorised');
  assert.equal(k({ status: 403 }), 'forbidden');
  assert.equal(k({ status: 404 }), 'not-found');
  assert.equal(k({ status: 429 }), 'rate-limited');
  assert.equal(k({ status: 503 }), 'unavailable');
  assert.equal(k({ status: 504 }), 'timeout');
  assert.equal(k({ error: new Error('The operation was aborted') }), 'timeout');
  assert.equal(k({ status: 0 }), 'offline');
  assert.equal(k({ error: new TypeError('Failed to fetch') }), 'offline');
  assert.equal(k({ error: new SyntaxError('Unexpected token < in JSON') }), 'invalid-response');
  assert.equal(k({}), 'unknown');
});

test('only transient failures are retryable; auth and missing data are not', () => {
  assert.equal(lf.describeLoadFailure({ status: 503 }).retryable, true);
  assert.equal(lf.describeLoadFailure({ status: 0 }).retryable, true);
  assert.equal(lf.describeLoadFailure({ status: 401 }).retryable, false);
  assert.equal(lf.describeLoadFailure({ status: 404 }).retryable, false);
});

test('server detail is shown only when it is short plain text', () => {
  assert.equal(lf.describeLoadFailure({ status: 503, detail: 'engine warming up' }).detail, 'engine warming up');
  assert.equal(lf.describeLoadFailure({ status: 502, detail: '<html><body>Bad gateway</body></html>' }).detail, null);
  assert.equal(lf.describeLoadFailure({ status: 500, detail: { nested: true } }).detail, null);
  assert.equal(lf.describeLoadFailure({ status: 500, detail: 'x'.repeat(400) }).detail.length, 160);
});

test('failureFromResult is null for ok results and maps ApiResult failures', () => {
  assert.equal(lf.failureFromResult({ ok: true, status: 200, data: {}, error: null }), null);
  const f = lf.failureFromResult({ ok: false, status: 503, data: null, error: 'Service Unavailable' });
  assert.equal(f.kind, 'unavailable');
});

test('readJsonOrThrow returns bodies for 2xx and throws classified failures otherwise', async () => {
  const res = (ok, status, body) => ({ ok, status, json: async () => { if (body instanceof Error) throw body; return body; } });
  assert.deepEqual(await lf.readJsonOrThrow(res(true, 200, { a: 1 })), { a: 1 });
  await assert.rejects(lf.readJsonOrThrow(res(false, 503, { detail: 'offline (harness)' })), (e) => {
    assert.ok(e instanceof lf.LoadFailureError);
    assert.equal(e.failure.kind, 'unavailable');
    assert.equal(e.failure.detail, 'offline (harness)');
    return true;
  });
  await assert.rejects(lf.readJsonOrThrow(res(true, 200, new SyntaxError('bad'))), (e) => e.failure.kind === 'invalid-response');
  assert.equal(lf.failureFromError(new TypeError('Failed to fetch')).kind, 'offline');
  // apiController ApiError shapes
  const httpErr = Object.assign(new Error('HTTP 503'), { code: 'http', status: 503, body: { detail: 'maintenance' } });
  assert.deepEqual([lf.failureFromError(httpErr).kind, lf.failureFromError(httpErr).detail], ['unavailable', 'maintenance']);
  assert.equal(lf.failureFromError(Object.assign(new Error('Request timed out'), { code: 'timeout', status: 0 })).kind, 'timeout');
  assert.equal(lf.failureFromError(Object.assign(new Error('Network error'), { code: 'network', status: 0 })).kind, 'offline');
});

test('LoadingNotice is a named, busy progressbar', () => {
  const html = render(h(LoadingNotice, { what: 'worlds', testID: 'ld' }));
  assert.match(html, /role="progressbar"/);
  assert.ok(attrs(html, 'aria-label').includes('Loading worlds…'));
  assert.match(html, /aria-busy="true"/);
});

test('LoadErrorNotice is an alert with a named 44pt retry only when retrying can help', () => {
  let retried = 0;
  const transient = lf.describeLoadFailure({ status: 503, detail: 'engine warming up' });
  const html = render(h(LoadErrorNotice, { failure: transient, what: 'worlds', onRetry: () => { retried++; }, testID: 'err' }));
  assert.match(html, /role="alert"/);
  assert.match(text(html), /Could not load worlds/);
  assert.match(text(html), /unavailable right now/);
  assert.match(text(html), /engine warming up/);
  assert.ok(attrs(html, 'aria-label').includes('Try again: worlds'));
  assert.match(html, /min-height:\s*44px/);
  const auth = render(h(LoadErrorNotice, { failure: lf.describeLoadFailure({ status: 401 }), what: 'worlds', onRetry: () => {} }));
  assert.doesNotMatch(auth, /role="button"/);
  assert.equal(retried, 0);
});

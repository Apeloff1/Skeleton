import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  boundedRetries, boundedTimeoutMs, boundedResponseChars, retryableHttpStatus, retryDelayMs,
} from '../utils/requestRecoveryPolicy.ts';

test('safe GET can retry within a finite budget', () => {
  assert.equal(boundedRetries(undefined, 'GET', false), 2);
  assert.equal(boundedRetries(1_000_000, 'GET', false), 3);
  assert.equal(boundedRetries(Number.POSITIVE_INFINITY, 'GET', false), 0);
  assert.equal(boundedRetries(-9, 'GET', false), 0);
});

test('writes never replay without explicit idempotency identity', () => {
  for (const method of ['POST', 'PUT', 'PATCH', 'DELETE']) {
    assert.equal(boundedRetries(undefined, method, false), 0, method);
    assert.equal(boundedRetries(50, method, false), 0, method);
    // A client-generated key alone is NOT proof that the server deduplicates.
    assert.equal(boundedRetries(9, method, true), 0, method);
    assert.equal(boundedRetries(9, method, true, true), 3, method);
  }
});

test('timeouts and retry waits are always finite', () => {
  assert.equal(boundedTimeoutMs(0), 250);
  assert.equal(boundedTimeoutMs(1_000_000), 30_000);
  assert.equal(boundedTimeoutMs(Number.NaN), 12_000);
  assert.equal(retryDelayMs(0), 400);
  assert.equal(retryDelayMs(30), 8_000);
  assert.equal(retryDelayMs(Number.POSITIVE_INFINITY), 400);
});

test('only transient HTTP responses are retryable', () => {
  for (const code of [408, 429, 500, 502, 503, 504, 599]) assert.equal(retryableHttpStatus(code), true);
  for (const code of [200, 400, 401, 403, 404, 409, 422]) assert.equal(retryableHttpStatus(code), false);
});

test('large game responses have an explicit finite size budget', () => {
  assert.equal(boundedResponseChars(undefined), 8 * 1024 * 1024);
  assert.equal(boundedResponseChars(1), 1024);
  assert.equal(boundedResponseChars(128 * 1024 * 1024), 64 * 1024 * 1024);
  assert.equal(boundedResponseChars(Number.POSITIVE_INFINITY), 8 * 1024 * 1024);
});

test('malformed retry requests fail closed despite a claimed idempotency key', () => {
  for (const value of [Number.NaN, Number.POSITIVE_INFINITY, -100]) {
    assert.equal(boundedRetries(value, 'POST', true, true), 0);
  }
  assert.equal(boundedRetries(2, 'POST', false, true), 0);
});

import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  LAUNCH_ATTEMPT_TTL_MS,
  readLaunchAttempt,
  writeLaunchAttempt,
  shouldAcceptLocalBoot,
} from '../src/boot/recoveryPolicy.ts';

test('a recorded fallback survives a recent successful boot cache', () => {
  const now = 1_800_000_000_000;
  const receipt = writeLaunchAttempt(2, now);
  assert.equal(readLaunchAttempt(receipt, now + 60_000), 2);
});

test('fallback attempts expire based on their own age', () => {
  const now = 1_800_000_000_000;
  const receipt = writeLaunchAttempt(3, now);
  assert.equal(readLaunchAttempt(receipt, now + LAUNCH_ATTEMPT_TTL_MS), 3);
  assert.equal(readLaunchAttempt(receipt, now + LAUNCH_ATTEMPT_TTL_MS + 1), 0);
});

test('corrupt, future-dated and non-numeric recovery receipts fail safely', () => {
  const now = 1_800_000_000_000;
  for (const receipt of ['{', '{}', 'null', '"3"', '{"layer":2,"at":"tomorrow"}', '{"layer":2,"at":1800000000001}']) {
    assert.equal(readLaunchAttempt(receipt, now), 0, receipt);
  }
  assert.equal(readLaunchAttempt(null, now), 0);
});

test('legacy numeric fallbacks survive deployment and clamp to known layers', () => {
  assert.equal(readLaunchAttempt('2'), 2);
  assert.equal(readLaunchAttempt('900'), 3);
  assert.equal(readLaunchAttempt('-5'), 0);
  assert.equal(writeLaunchAttempt(0), '0');
});

test('no watchdog, cache, or pressure path can report readiness before phase-0 succeeds', () => {
  for (const phaseDone of [false, true]) {
    for (const criticalOk of [false, true]) {
      assert.equal(shouldAcceptLocalBoot(phaseDone, criticalOk), phaseDone && criticalOk);
    }
  }
});

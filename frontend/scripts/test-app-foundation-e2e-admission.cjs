'use strict';
/**
 * Exercise full-live E2E admission in a genuine Node child process.
 * The fixture token and dead loopback URL never authorize a real build.
 */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const { resolve, join } = require('node:path');
const { mkdtempSync, writeFileSync, rmSync } = require('node:fs');
const { tmpdir } = require('node:os');

const suite = resolve(__dirname, 'test-app-foundation-flows.mjs');

function launch(overrides, removed = []) {
  const env = { ...process.env, SKELETON_E2E_REQUIRE_FULL_LIVE: '1', ...overrides };
  for (const key of removed) delete env[key];
  return spawnSync(process.execPath, ['--test', suite], {
    env, encoding: 'utf8', timeout: 20_000, maxBuffer: 1024 * 1024,
  });
}

test('full live refuses an absent operator token before contacting the backend', () => {
  const child = launch({ SKELETON_E2E_BASE_URL: 'http://127.0.0.1:1' },
                       ['SKELETON_E2E_OPERATOR_TOKEN_FILE']);
  assert.equal(child.error, undefined);
  assert.notEqual(child.status, 0, 'a skipped privileged step must not certify E2E');
  assert.match(child.stdout + child.stderr,
               /full live E2E requires authorized operator token/);
});

test('full live refuses an absent backend even with a fixture operator token', () => {
  const dir = mkdtempSync(join(tmpdir(), 'skeleton-e2e-admission-'));
  try {
    const token = join(dir, 'fixture-token');
    writeFileSync(token, 'fixture-only-not-an-operator', { mode: 0o600 });
    const child = launch({ SKELETON_E2E_OPERATOR_TOKEN_FILE: token },
                         ['SKELETON_E2E_BASE_URL']);
    assert.equal(child.error, undefined);
    assert.notEqual(child.status, 0, 'a missing live backend cannot qualify');
    assert.match(child.stdout + child.stderr,
                 /full live E2E requires SKELETON_E2E_BASE_URL/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

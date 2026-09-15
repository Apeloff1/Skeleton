#!/usr/bin/env node
/* eslint-disable */
const assert = require('assert');
const { spawnSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const policy = path.join(__dirname, 'enforce-yarn-audit.js');
const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'yarn-audit-policy-'));

const summary = (high = 0, critical = 0, overrides = {}) => ({
  type: 'auditSummary',
  data: {
    vulnerabilities: {
      info: 0,
      low: 0,
      moderate: 0,
      high,
      critical,
      ...overrides,
    },
    dependencies: 1,
    devDependencies: 0,
    optionalDependencies: 0,
    totalDependencies: 1,
  },
});

const advisory = ({
  module = 'example-package',
  severity = 'high',
  ghsa = 'GHSA-xxxx-yyyy-zzzz',
  title = 'test advisory',
} = {}) => ({
  type: 'auditAdvisory',
  data: {
    advisory: {
      module_name: module,
      severity,
      github_advisory_id: ghsa,
      title,
    },
  },
});

function runCase(name, lines, status) {
  const auditPath = path.join(tempRoot, `${name}.json`);
  fs.writeFileSync(auditPath, lines.join('\n'), 'utf8');
  return spawnSync(process.execPath, [policy, auditPath], {
    encoding: 'utf8',
    env: {
      ...process.env,
      IMAGE_SIZE_SECURITY_VERIFIED: 'success',
      YARN_AUDIT_STATUS: String(status),
    },
  });
}

function expectPass(name, lines, status) {
  const result = runCase(name, lines, status);
  assert.strictEqual(
    result.status,
    0,
    `${name} should pass\nstdout:\n${result.stdout}\nstderr:\n${result.stderr}`,
  );
}

function expectFail(name, lines, status) {
  const result = runCase(name, lines, status);
  assert.notStrictEqual(
    result.status,
    0,
    `${name} should fail\nstdout:\n${result.stdout}\nstderr:\n${result.stderr}`,
  );
}

try {
  expectPass('clean', [JSON.stringify(summary())], 0);
  expectPass(
    'moderate-only-mask',
    [JSON.stringify(summary(0, 0, { moderate: 2 }))],
    4,
  );
  expectPass(
    'lower-severity-combined-mask',
    [JSON.stringify(summary(0, 0, { info: 1, moderate: 2 }))],
    5,
  );

  expectFail('empty', [], 1);
  expectFail('malformed-json', ['{not-json'], 1);
  expectFail('status-outside-yarn-mask', [JSON.stringify(summary())], 32);
  expectFail(
    'audit-error-record',
    [JSON.stringify({ type: 'error', data: 'registry unavailable' }), JSON.stringify(summary())],
    1,
  );
  expectFail(
    'missing-summary',
    [JSON.stringify(advisory())],
    8,
  );
  expectFail(
    'duplicate-summary',
    [JSON.stringify(summary()), JSON.stringify(summary())],
    0,
  );
  expectFail(
    'negative-summary-count',
    [JSON.stringify(summary(0, 0, { moderate: -1 }))],
    0,
  );
  expectFail(
    'fractional-summary-count',
    [JSON.stringify(summary(0, 0, { low: 0.5 }))],
    0,
  );
  expectFail(
    'string-summary-count',
    [JSON.stringify(summary(0, 0, { high: '0' }))],
    0,
  );
  expectFail(
    'status-summary-mask-mismatch',
    [JSON.stringify(summary(0, 0, { moderate: 1 }))],
    8,
  );
  expectFail(
    'summary-without-advisory-detail',
    [JSON.stringify(summary(1, 0))],
    8,
  );
  expectFail(
    'malformed-advisory',
    [JSON.stringify({ type: 'auditAdvisory', data: {} }), JSON.stringify(summary())],
    0,
  );
  expectFail(
    'unknown-advisory-severity',
    [JSON.stringify(advisory({ severity: 'severe' })), JSON.stringify(summary())],
    0,
  );
  expectFail(
    'zero-status-with-blocking-summary',
    [
      JSON.stringify(
        advisory({
          module: 'image-size',
          ghsa: 'GHSA-5p2g-fcmc-qvqq',
          title: 'mitigated parser progress flaw',
        }),
      ),
      JSON.stringify(summary(1, 0)),
    ],
    0,
  );
  expectPass(
    'mitigated-image-size',
    [
      JSON.stringify(
        advisory({
          module: 'image-size',
          ghsa: 'GHSA-5p2g-fcmc-qvqq',
          title: 'mitigated parser progress flaw',
        }),
      ),
      JSON.stringify(summary(1, 0)),
    ],
    8,
  );
  expectFail(
    'unmitigated-high',
    [JSON.stringify(advisory()), JSON.stringify(summary(1, 0))],
    8,
  );

  console.log('yarn audit policy regression tests passed');
} finally {
  fs.rmSync(tempRoot, { recursive: true, force: true });
}

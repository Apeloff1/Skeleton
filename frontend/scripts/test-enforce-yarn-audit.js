#!/usr/bin/env node
/* eslint-disable */
const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

const policy = path.join(__dirname, 'enforce-yarn-audit.js');
const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'yarn-audit-policy-'));

const advisory = ({ module, severity, ghsa, title = 'fixture advisory' }) => ({
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

const summary = { type: 'auditSummary', data: { vulnerabilities: {} } };

function runCase(name, records, status, expectedExit, imageVerifier = 'success') {
  const report = path.join(tempDir, `${name}.json`);
  fs.writeFileSync(
    report,
    records.map((record) => (typeof record === 'string' ? record : JSON.stringify(record))).join('\n') + '\n',
    'utf8',
  );
  const result = spawnSync(process.execPath, [policy, report], {
    env: {
      ...process.env,
      IMAGE_SIZE_SECURITY_VERIFIED: imageVerifier,
      YARN_AUDIT_STATUS: String(status),
    },
    encoding: 'utf8',
  });
  assert.strictEqual(
    result.status,
    expectedExit,
    `${name}: expected exit ${expectedExit}, got ${result.status}\nstdout=${result.stdout}\nstderr=${result.stderr}`,
  );
}

try {
  runCase('clean', [summary], 0, 0);
  runCase(
    'mitigated-high',
    [advisory({ module: 'image-size', severity: 'high', ghsa: 'GHSA-5p2g-fcmc-qvqq' }), summary],
    8,
    0,
  );
  runCase(
    'unmitigated-critical',
    [advisory({ module: 'fixture-package', severity: 'critical', ghsa: 'GHSA-test-test-test' }), summary],
    16,
    1,
  );
  runCase('missing-summary', [advisory({ module: 'fixture-package', severity: 'high', ghsa: 'GHSA-test-test-test' })], 8, 2);
  runCase('status-mismatch', [summary], 1, 2);
  runCase('malformed-json', ['{not-json'], 0, 2);
  runCase('verifier-failure', [summary], 0, 1, 'failure');
  console.log('[yarn-audit-policy-test] all regression cases passed');
} finally {
  fs.rmSync(tempDir, { recursive: true, force: true });
}

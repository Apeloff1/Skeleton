#!/usr/bin/env node
/* eslint-disable */
const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

const policy = path.join(__dirname, 'enforce-yarn-audit.js');
const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'yarn-audit-policy-'));

function assertBraceExpansionResolutionLock() {
  const frontendRoot = path.resolve(__dirname, '..');
  const packageJson = JSON.parse(
    fs.readFileSync(path.join(frontendRoot, 'package.json'), 'utf8'),
  );
  const lock = fs.readFileSync(path.join(frontendRoot, 'yarn.lock'), 'utf8');
  const expectedVersion = '1.1.21';
  const expectedIntegrity =
    'sha512-9zeA+KLZNNzglF2TPKRQEDyx6Yby7daAkuy8MiPzpXPsYDWi/DRM8jmwUDxokQjYqBpv5DgPiwD4h4ZZSy1Ujw==';

  assert.strictEqual(
    packageJson.resolutions['**/minimatch/brace-expansion'],
    expectedVersion,
    'brace-expansion resolution must stay on the reviewed patched release',
  );

  const selector =
    'brace-expansion@1.1.21, brace-expansion@^1.1.7, brace-expansion@^2.0.2, brace-expansion@^5.0.5:';
  const start = lock.indexOf(selector);
  assert.notStrictEqual(start, -1, 'brace-expansion lock selector missing');
  const nextEntry = lock.indexOf('\n\n', start);
  const block = lock.slice(start, nextEntry === -1 ? undefined : nextEntry);

  assert.match(block, /version "1\.1\.21"/);
  assert.match(
    block,
    /resolved "https:\/\/registry\.yarnpkg\.com\/brace-expansion\/-\/brace-expansion-1\.1\.21\.tgz"/,
  );
  assert.ok(
    block.includes(`integrity ${expectedIntegrity}`),
    'brace-expansion lock integrity must match the reviewed 1.1.21 artifact',
  );
  assert.ok(
    !block.includes('brace-expansion-1.1.20.tgz') && !block.includes('version "1.1.20"'),
    'brace-expansion lock must not silently retain the vulnerable 1.1.20 payload',
  );
}

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

const summary = (overrides = {}) => ({
  type: 'auditSummary',
  data: {
    vulnerabilities: {
      info: 0,
      low: 0,
      moderate: 0,
      high: 0,
      critical: 0,
      ...overrides,
    },
  },
});

function runCase(
  name,
  records,
  status,
  expectedExit,
  imageVerifier = 'success',
  npmVerifier = 'success',
) {
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
      NPM_COMPENSATING_SECURITY_VERIFIED: npmVerifier,
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
  assertBraceExpansionResolutionLock();
  runCase('clean', [summary()], 0, 0);
  runCase('filtered-low-mask', [summary({ low: 1 })], 2, 0);
  runCase('filtered-moderate-mask', [summary({ moderate: 1 })], 4, 0);
  runCase('filtered-info-low-moderate-mask', [summary({ info: 1, low: 1, moderate: 1 })], 7, 0);
  runCase(
    'mitigated-high',
    [advisory({ module: 'image-size', severity: 'high', ghsa: 'GHSA-5p2g-fcmc-qvqq' }), summary({ high: 1 })],
    8,
    0,
  );
  runCase(
    'mitigated-high-with-filtered-lower-bits',
    [
      advisory({ module: 'image-size', severity: 'high', ghsa: 'GHSA-w3rx-r6r6-pgpr' }),
      summary({ info: 1, low: 1, moderate: 1, high: 1 }),
    ],
    15,
    0,
  );
  runCase(
    'mitigated-braces-no-release',
    [advisory({ module: 'braces', severity: 'high', ghsa: 'GHSA-vfj7-8cjw-p6xm' }), summary({ high: 1 })],
    8,
    0,
  );
  runCase(
    'mitigated-http-cache-no-release',
    [advisory({ module: 'http-cache-semantics', severity: 'high', ghsa: 'GHSA-ch52-4w7c-c8xp' }), summary({ high: 1 })],
    8,
    0,
  );
  runCase(
    'mitigated-node-forge-no-release',
    [advisory({ module: 'node-forge', severity: 'high', ghsa: 'GHSA-86w9-cpqp-85rv' }), summary({ high: 1 })],
    8,
    0,
  );
  runCase(
    'mitigation-is-package-bound',
    [advisory({ module: 'fixture-package', severity: 'high', ghsa: 'GHSA-vfj7-8cjw-p6xm' }), summary({ high: 1 })],
    8,
    1,
  );
  runCase(
    'unmitigated-critical',
    [advisory({ module: 'fixture-package', severity: 'critical', ghsa: 'GHSA-test-test-test' }), summary({ critical: 1 })],
    16,
    1,
  );
  runCase(
    'unmitigated-critical-with-filtered-lower-bits',
    [
      advisory({ module: 'fixture-package', severity: 'critical', ghsa: 'GHSA-test-test-test' }),
      summary({ info: 1, low: 1, moderate: 1, critical: 1 }),
    ],
    23,
    1,
  );
  runCase(
    'missing-summary',
    [advisory({ module: 'fixture-package', severity: 'high', ghsa: 'GHSA-test-test-test' })],
    8,
    2,
  );
  runCase('incomplete-summary', [{ type: 'auditSummary', data: { vulnerabilities: { high: 0, critical: 0 } } }], 0, 2);
  runCase('duplicate-summary', [summary(), summary()], 0, 2);
  runCase('blocking-status-mismatch', [summary()], 8, 2);
  runCase('summary-status-mismatch', [summary({ high: 1 })], 0, 2);
  runCase('malformed-record-shape', ['null'], 0, 2);
  runCase('malformed-json', ['{not-json'], 0, 2);
  runCase('image-verifier-failure', [summary()], 0, 1, 'failure');
  runCase('npm-verifier-failure', [summary()], 0, 1, 'success', 'failure');
  console.log('[yarn-audit-policy-test] all regression cases passed');
} finally {
  fs.rmSync(tempDir, { recursive: true, force: true });
}

#!/usr/bin/env node
/* eslint-disable */
const fs = require('fs');

const auditPath = process.argv[2];
if (!auditPath) {
  console.error('usage: node scripts/enforce-yarn-audit.js <yarn-audit.json>');
  process.exit(2);
}

if (process.env.IMAGE_SIZE_SECURITY_VERIFIED !== 'success') {
  console.error('[yarn-audit-policy] image-size security verifier did not succeed; blocking');
  process.exit(1);
}
if (process.env.NPM_COMPENSATING_SECURITY_VERIFIED !== 'success') {
  console.error('[yarn-audit-policy] no-release npm security verifier did not succeed; blocking');
  process.exit(1);
}

const rawAuditStatus = process.env.YARN_AUDIT_STATUS;
if (!/^\d+$/.test(String(rawAuditStatus || ''))) {
  console.error('[yarn-audit-policy] missing or invalid yarn audit exit status');
  process.exit(2);
}

const auditStatus = Number(rawAuditStatus);
if (!Number.isInteger(auditStatus) || auditStatus < 0 || auditStatus > 31) {
  console.error(`[yarn-audit-policy] unexpected yarn audit exit status: ${rawAuditStatus}`);
  process.exit(2);
}

const severityBits = Object.freeze({
  info: 1,
  low: 2,
  moderate: 4,
  high: 8,
  critical: 16,
});
const blockingSeverityMask = severityBits.high | severityBits.critical;
const severityNames = Object.keys(severityBits);

const allowedMitigatedAdvisories = new Map([
  [
    'image-size',
    new Set([
      // Metro 0.83.x requires image-size 1.x; parser progress is locally patched and behavior-tested.
      'GHSA-5p2g-fcmc-qvqq',
      'GHSA-w3rx-r6r6-pgpr',
    ]),
  ],
  [
    'braces',
    new Set([
      // CVE-2026-93687: public string entry points are depth-bounded locally.
      'GHSA-vfj7-8cjw-p6xm',
    ]),
  ],
  [
    'http-cache-semantics',
    new Set([
      // CVE-2026-93748: max-stale cannot resurrect security-zeroed entries.
      'GHSA-ch52-4w7c-c8xp',
    ]),
  ],
  [
    'node-forge',
    new Set([
      // CVE-2026-85393 current GHSA plus the upstream advisory alias.
      'GHSA-86w9-cpqp-85rv',
      'GHSA-ppp5-5v6c-4jwp',
    ]),
  ],
]);

const findings = [];
const mitigated = [];
let observedBlockingMask = 0;
let auditSummaryCount = 0;
let summaryVulnerabilities = null;

let auditText;
try {
  auditText = fs.readFileSync(auditPath, 'utf8');
} catch (error) {
  console.error('[yarn-audit-policy] audit report is missing or unreadable');
  process.exit(2);
}

for (const line of auditText.split(/\r?\n/)) {
  if (!line.trim()) continue;
  let record;
  try {
    record = JSON.parse(line);
  } catch (error) {
    console.error('[yarn-audit-policy] invalid JSON audit record');
    process.exit(2);
  }

  if (!record || typeof record !== 'object' || Array.isArray(record)) {
    console.error('[yarn-audit-policy] malformed audit record');
    process.exit(2);
  }

  if (record.type === 'error') {
    console.error('[yarn-audit-policy] yarn emitted an audit error record');
    process.exit(2);
  }
  if (record.type === 'auditSummary') {
    auditSummaryCount += 1;
    if (auditSummaryCount > 1) {
      console.error('[yarn-audit-policy] multiple audit summaries emitted; refusing ambiguous output');
      process.exit(2);
    }

    const vulnerabilities = record.data && record.data.vulnerabilities;
    if (!vulnerabilities || typeof vulnerabilities !== 'object' || Array.isArray(vulnerabilities)) {
      console.error('[yarn-audit-policy] malformed audit summary vulnerabilities');
      process.exit(2);
    }
    for (const severity of severityNames) {
      const count = vulnerabilities[severity];
      if (!Number.isInteger(count) || count < 0) {
        console.error(`[yarn-audit-policy] incomplete audit summary severity count: ${severity}`);
        process.exit(2);
      }
    }
    summaryVulnerabilities = vulnerabilities;
    continue;
  }
  if (record.type !== 'auditAdvisory') continue;

  const advisory = record.data && record.data.advisory;
  if (!advisory || typeof advisory !== 'object' || Array.isArray(advisory)) {
    console.error('[yarn-audit-policy] malformed audit advisory record');
    process.exit(2);
  }

  const severity = String(advisory.severity || '').toLowerCase();
  const severityBit = severityBits[severity];
  if (!severityBit) {
    console.error(`[yarn-audit-policy] unknown advisory severity: ${severity || 'missing'}`);
    process.exit(2);
  }

  // Yarn Classic's --level flag filters printed advisories but intentionally
  // does not filter the process exit mask. Reconcile only the blocking bits
  // that the high-level JSON stream is guaranteed to expose.
  if (!['high', 'critical'].includes(severity)) continue;
  observedBlockingMask |= severityBit;

  const ghsa = String(advisory.github_advisory_id || '');
  const item = {
    module: String(advisory.module_name || 'unknown'),
    severity,
    ghsa,
    title: String(advisory.title || ''),
  };
  const moduleAllowlist = allowedMitigatedAdvisories.get(item.module);
  if (moduleAllowlist && moduleAllowlist.has(ghsa)) {
    mitigated.push(item);
  } else {
    findings.push(item);
  }
}

if (auditSummaryCount !== 1 || !summaryVulnerabilities) {
  console.error('[yarn-audit-policy] audit summary missing; refusing to treat incomplete output as clean');
  process.exit(2);
}

const reportedBlockingMask = auditStatus & blockingSeverityMask;
if (reportedBlockingMask !== observedBlockingMask) {
  console.error(
    `[yarn-audit-policy] yarn blocking-severity mask ${reportedBlockingMask} does not match parsed mask ${observedBlockingMask}`,
  );
  process.exit(2);
}

const summaryBlockingMask =
  (summaryVulnerabilities.high > 0 ? severityBits.high : 0) |
  (summaryVulnerabilities.critical > 0 ? severityBits.critical : 0);
if (summaryBlockingMask !== reportedBlockingMask) {
  console.error(
    `[yarn-audit-policy] audit summary blocking-severity mask ${summaryBlockingMask} does not match process mask ${reportedBlockingMask}`,
  );
  process.exit(2);
}

const unique = (items) => {
  const seen = new Set();
  return items.filter((item) => {
    const key = `${item.module}:${item.ghsa}:${item.title}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
};

for (const item of unique(mitigated)) {
  console.log(`[yarn-audit-policy] mitigated ${item.severity}: ${item.module} ${item.ghsa}`);
}

const remaining = unique(findings);
if (remaining.length) {
  for (const item of remaining) {
    console.error(`[yarn-audit-policy] ${item.severity}: ${item.module} ${item.ghsa} ${item.title}`);
  }
  console.error(`[yarn-audit-policy] blocking on ${remaining.length} unique high/critical advisories`);
  process.exit(1);
}

console.log('[yarn-audit-policy] no unmitigated high/critical advisories');

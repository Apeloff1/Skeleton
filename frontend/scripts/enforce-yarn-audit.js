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

const allowedMitigatedAdvisories = new Set([
  // image-size has no patched npm release. These two parser-progress flaws are
  // patched fail-closed by scripts/patch-node-modules.js and verified by
  // scripts/verify-image-size-security.js before this policy is evaluated.
  'GHSA-5p2g-fcmc-qvqq',
  'GHSA-w3rx-r6r6-pgpr',
]);

const findings = [];
const mitigated = [];
let observedSeverityMask = 0;
let sawAuditSummary = false;

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

  if (record.type === 'error') {
    console.error('[yarn-audit-policy] yarn emitted an audit error record');
    process.exit(2);
  }
  if (record.type === 'auditSummary') {
    sawAuditSummary = true;
    continue;
  }
  if (record.type !== 'auditAdvisory') continue;

  const advisory = record.data && record.data.advisory;
  if (!advisory) {
    console.error('[yarn-audit-policy] malformed audit advisory record');
    process.exit(2);
  }

  const severity = String(advisory.severity || '').toLowerCase();
  const severityBit = severityBits[severity];
  if (!severityBit) {
    console.error(`[yarn-audit-policy] unknown advisory severity: ${severity || 'missing'}`);
    process.exit(2);
  }
  observedSeverityMask |= severityBit;

  if (!['high', 'critical'].includes(severity)) continue;
  const ghsa = String(advisory.github_advisory_id || '');
  const item = {
    module: String(advisory.module_name || 'unknown'),
    severity,
    ghsa,
    title: String(advisory.title || ''),
  };
  if (item.module === 'image-size' && allowedMitigatedAdvisories.has(ghsa)) {
    mitigated.push(item);
  } else {
    findings.push(item);
  }
}

if (!sawAuditSummary) {
  console.error('[yarn-audit-policy] audit summary missing; refusing to treat incomplete output as clean');
  process.exit(2);
}

if (auditStatus !== observedSeverityMask) {
  console.error(
    `[yarn-audit-policy] yarn exit mask ${auditStatus} does not match parsed advisory mask ${observedSeverityMask}`,
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

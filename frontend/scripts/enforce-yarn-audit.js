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
if (!rawAuditStatus || !/^\d+$/.test(rawAuditStatus)) {
  console.error('[yarn-audit-policy] missing or invalid YARN_AUDIT_STATUS; blocking');
  process.exit(2);
}
const auditStatus = Number(rawAuditStatus);
if (!Number.isSafeInteger(auditStatus) || auditStatus < 0 || auditStatus > 31) {
  console.error('[yarn-audit-policy] YARN_AUDIT_STATUS is outside the Yarn severity bitmask; blocking');
  process.exit(2);
}

const severities = ['info', 'low', 'moderate', 'high', 'critical'];
const severityBits = {
  info: 1,
  low: 2,
  moderate: 4,
  high: 8,
  critical: 16,
};

const allowedMitigatedAdvisories = new Set([
  // image-size has no patched npm release. These two parser-progress flaws are
  // patched fail-closed by scripts/patch-node-modules.js and verified by
  // scripts/verify-image-size-security.js before this policy is evaluated.
  'GHSA-5p2g-fcmc-qvqq',
  'GHSA-w3rx-r6r6-pgpr',
]);

let auditText;
try {
  auditText = fs.readFileSync(auditPath, 'utf8');
} catch (error) {
  console.error(`[yarn-audit-policy] unable to read audit transcript: ${error.message}`);
  process.exit(2);
}

const findings = [];
const mitigated = [];
const auditErrors = [];
let sawRecord = false;
let summary = null;
let summaryCount = 0;

for (const line of auditText.split(/\r?\n/)) {
  if (!line.trim()) continue;
  sawRecord = true;
  let record;
  try {
    record = JSON.parse(line);
  } catch (error) {
    console.error('[yarn-audit-policy] invalid JSON audit record');
    process.exit(2);
  }

  if (!record || typeof record !== 'object' || Array.isArray(record) || typeof record.type !== 'string') {
    console.error('[yarn-audit-policy] malformed audit record; blocking');
    process.exit(2);
  }

  if (record.type === 'error') {
    auditErrors.push(record);
    continue;
  }

  if (record.type === 'auditSummary') {
    summaryCount += 1;
    if (summaryCount !== 1) {
      console.error('[yarn-audit-policy] multiple auditSummary records; blocking');
      process.exit(2);
    }
    const data = record.data;
    if (
      !data ||
      typeof data !== 'object' ||
      Array.isArray(data) ||
      !data.vulnerabilities ||
      typeof data.vulnerabilities !== 'object' ||
      Array.isArray(data.vulnerabilities)
    ) {
      console.error('[yarn-audit-policy] malformed audit summary; blocking');
      process.exit(2);
    }
    for (const severity of severities) {
      const value = data.vulnerabilities[severity];
      if (!Number.isSafeInteger(value) || value < 0) {
        console.error(`[yarn-audit-policy] invalid ${severity} vulnerability count; blocking`);
        process.exit(2);
      }
    }
    summary = data;
    continue;
  }

  if (record.type !== 'auditAdvisory') continue;
  const advisory = record.data && record.data.advisory;
  if (!advisory || typeof advisory !== 'object' || Array.isArray(advisory)) {
    console.error('[yarn-audit-policy] malformed audit advisory; blocking');
    process.exit(2);
  }
  const severity = String(advisory.severity || '');
  if (!severities.includes(severity)) {
    console.error('[yarn-audit-policy] audit advisory has unknown severity; blocking');
    process.exit(2);
  }
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

if (!sawRecord) {
  console.error('[yarn-audit-policy] empty audit transcript; blocking');
  process.exit(2);
}
if (auditErrors.length) {
  console.error(`[yarn-audit-policy] yarn audit emitted ${auditErrors.length} error record(s); blocking`);
  process.exit(2);
}
if (!summary) {
  console.error('[yarn-audit-policy] audit transcript ended without auditSummary; blocking');
  process.exit(2);
}

const vulnerabilityCounts = summary.vulnerabilities;
const expectedStatus = severities.reduce(
  (mask, severity) => mask | (vulnerabilityCounts[severity] > 0 ? severityBits[severity] : 0),
  0,
);
if (auditStatus !== expectedStatus) {
  console.error(
    `[yarn-audit-policy] yarn audit status ${auditStatus} disagrees with summary severity mask ${expectedStatus}; blocking`,
  );
  process.exit(2);
}

const blockingSummaryCount = vulnerabilityCounts.high + vulnerabilityCounts.critical;
const observedBlockingAdvisories = findings.length + mitigated.length;
if ((blockingSummaryCount > 0) !== (observedBlockingAdvisories > 0)) {
  console.error(
    '[yarn-audit-policy] high/critical audit summary and advisory detail disagree; blocking',
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

if (auditStatus !== 0) {
  console.log(
    `[yarn-audit-policy] yarn audit exited ${auditStatus}; complete transcript contains only policy-allowed findings at the blocking severities`,
  );
}
console.log('[yarn-audit-policy] no unmitigated high/critical advisories');

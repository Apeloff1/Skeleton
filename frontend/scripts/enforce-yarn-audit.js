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

  if (record.type === 'error') {
    auditErrors.push(record);
    continue;
  }

  if (record.type === 'auditSummary') {
    const data = record.data;
    if (
      !data ||
      typeof data !== 'object' ||
      !data.vulnerabilities ||
      typeof data.vulnerabilities !== 'object'
    ) {
      console.error('[yarn-audit-policy] malformed audit summary; blocking');
      process.exit(2);
    }
    summary = data;
    continue;
  }

  if (record.type !== 'auditAdvisory') continue;
  const advisory = record.data && record.data.advisory;
  if (!advisory) continue;
  if (!['high', 'critical'].includes(String(advisory.severity))) continue;
  const ghsa = String(advisory.github_advisory_id || '');
  const item = {
    module: String(advisory.module_name || 'unknown'),
    severity: String(advisory.severity || 'unknown'),
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

const severityCount = (name) => {
  const value = Number(summary.vulnerabilities[name] || 0);
  return Number.isFinite(value) && value >= 0 ? value : 0;
};
const blockingSummaryCount = severityCount('high') + severityCount('critical');
const observedBlockingAdvisories = findings.length + mitigated.length;
if ((blockingSummaryCount > 0) !== (observedBlockingAdvisories > 0)) {
  console.error(
    '[yarn-audit-policy] high/critical audit summary and advisory detail disagree; blocking',
  );
  process.exit(2);
}
if (auditStatus !== 0 && blockingSummaryCount === 0) {
  console.error(
    `[yarn-audit-policy] yarn audit exited ${auditStatus} without high/critical findings; treating as execution failure`,
  );
  process.exit(2);
}
if (auditStatus === 0 && blockingSummaryCount > 0) {
  console.error(
    '[yarn-audit-policy] audit status contradicts high/critical summary; blocking',
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
    `[yarn-audit-policy] yarn audit exited ${auditStatus}; complete transcript contains only policy-mitigated high/critical advisories`,
  );
}
console.log('[yarn-audit-policy] no unmitigated high/critical advisories');

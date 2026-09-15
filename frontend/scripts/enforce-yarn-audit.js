#!/usr/bin/env node
/* eslint-disable */
const fs = require('fs');

const auditPath = process.argv[2];
if (!auditPath) {
  console.error('usage: node scripts/enforce-yarn-audit.js <yarn-audit.json>');
  process.exit(2);
}

const allowedMitigatedAdvisories = new Set([
  // image-size has no patched npm release. These two parser-progress flaws are
  // patched fail-closed by scripts/patch-node-modules.js and verified by
  // scripts/verify-image-size-security.js before this policy is evaluated.
  'GHSA-5p2g-fcmc-qvqq',
  'GHSA-w3rx-r6r6-pgpr',
]);

const findings = [];
const mitigated = [];
for (const line of fs.readFileSync(auditPath, 'utf8').split(/\r?\n/)) {
  if (!line.trim()) continue;
  let record;
  try {
    record = JSON.parse(line);
  } catch (error) {
    console.error('[yarn-audit-policy] invalid JSON audit record');
    process.exit(2);
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

'use strict';

/** Scoped, offline Yarn v1 security custody; does not suppress Dependabot.
 * Advisory snapshot: 2026-11-02. This is a scoped lockfile observation, not a
 * complete dependency audit or production release certification. Default
 * fails for affected or unreviewed versions. Use --report-only for evidence.
 */
const fs = require('node:fs');
const path = require('node:path');

const PATCHES = Object.freeze({
  'image-size': { fixed: { 2: '2.0.3' }, advisory: 'GHSA-5p2g-fcmc-qvqq / GHSA-w3rx-r6r6-pgpr' },
  'brace-expansion': { fixed: { 1: '1.1.21', 2: '2.1.7', 3: '3.0.9', 5: '5.0.12' }, advisory: 'GHSA-q2hr-2g5m-vwhr' },
  'decode-uri-component': { fixed: { 0: '0.5.1' }, severity: 'high', advisory: 'GHSA-vcc3-ghjq-m6fr / GHSA-qr28-fpjm-wq7f' },
  'undici': { fixed: { 6: '6.29.1', 7: '7.30.1', 8: '8.12.2' }, advisory: 'GHSA-xjj6-f33q-929c / GHSA-2m5v-pch6-74hx / GHSA-qrxm-fqhp-jwvm' },
  'zod': { fixed: { 4: '4.6.6' }, severity: 'high', advisory: 'GHSA-mrhx-c7xc-m3w5' },
});
// Range policies distinguish published fixed releases from exact versions that
// were independently reviewed outside an affected range. The latter are NOT a
// claim that upstream published a fix. Future versions remain blocked pending
// fresh advisory review.
const RANGES = Object.freeze({
  'follow-redirects': { affectedFrom: '1.16.0', affectedUpTo: '1.16.1', fixed: { 1: '1.16.2' }, reviewedOutside: [], severity: 'high', advisory: 'GHSA-mrwp-f3q8-3g9p' },
  'glob': { affectedFrom: '9.0.0', affectedUpTo: '14.0.1', fixed: { 14: '14.0.2' }, reviewedOutside: ['7.2.3'], severity: 'moderate', advisory: 'GHSA-3g3m-2fjr-6pw4' },
  'minimatch': { affectedFrom: '7.0.0', affectedUpTo: '11.0.0', fixed: { 11: '11.0.1' }, reviewedOutside: ['3.1.5'], severity: 'moderate', advisory: 'GHSA-g3hv-75wg-m249' },
  'http-cache-semantics': { affectedUpTo: '4.2.0', reviewedOutside: ['4.3.0'], advisory: 'GHSA-ch52-4w7c-c8xp' },
  // 1.4.3 requalified 2026-11-12 against exact upstream canonical-DER
  // RSA source, independent structure checks and a negative signature probe.
  // This scoped snapshot is not a blanket audit of future node-forge releases.
  'node-forge': { affectedUpTo: '1.4.0', reviewedOutside: ['1.4.2', '1.4.3'], advisory: 'GHSA-86w9-cpqp-85rv' },
  'deepmerge': { affectedFrom: '4.2.0', affectedUpTo: '4.3.1', reviewedOutside: ['4.3.2'], severity: 'low', advisory: 'GHSA-gcqx-w48m-w2h4' },
});
// GHSA-vfj7-8cjw-p6xm was officially withdrawn on 2026-10-23. This status
// applies only to that advisory and does not dismiss other braces findings.
const WITHDRAWN = Object.freeze({
  braces: { advisory: 'GHSA-vfj7-8cjw-p6xm', withdrawnAt: '2026-10-23T12:53:02Z' },
});
const TRACKED = Object.freeze([...Object.keys(PATCHES), ...Object.keys(RANGES), ...Object.keys(WITHDRAWN)]);

function versionParts(value) {
  if (typeof value !== 'string' || !/^\d+\.\d+\.\d+$/.test(value))
    throw new Error('unparseable pinned package version');
  const parts = value.split('.').map(Number);
  if (parts.some(part => !Number.isSafeInteger(part))) throw new Error('unparseable pinned package version');
  return parts;
}
function compareVersions(a, b) {
  const x = versionParts(a), y = versionParts(b);
  for (let i = 0; i < 3; i++) if (x[i] !== y[i]) return x[i] < y[i] ? -1 : 1;
  return 0;
}
function packageName(selector) {
  const s = selector.trim().replace(/^"/, '').replace(/"$/, '');
  const at = s.lastIndexOf('@');
  if (at < 1) throw new Error('invalid Yarn selector');
  return s.slice(0, at);
}

/** Parse only the pinned package metadata needed for this bounded audit.
 * Reject ambiguous stanzas, missing versions and unsupported lock versions.
 */
function parseYarnV1(source) {
  if (typeof source !== 'string' || !source.split('\n').slice(0, 5).includes('# yarn lockfile v1'))
    throw new Error('expected Yarn classic lockfile v1');
  const rows = [];
  const seenSelectors = new Set();
  for (const raw of source.split(/\n\s*\n/)) {
    const lines = raw.split('\n');
    if (!lines[0] || lines[0].startsWith('#')) continue;
    if (!/^[^\s#:][^\n]*:\s*$/.test(lines[0]) && !/^"[^\n]+"(?:,\s*"[^\n]+")*:\s*$/.test(lines[0]))
      throw new Error('unrecognized Yarn lock stanza');
    const header = lines[0].replace(/:\s*$/, '');
    const selectors = header.match(/"[^"]+"|[^,\s]+/g) || [];
    for (const selector of selectors) {
      if (seenSelectors.has(selector)) throw new Error('duplicate Yarn selector: ' + selector);
      seenSelectors.add(selector);
    }
    const names = [...new Set(selectors.map(packageName))];
    if (names.length !== 1) throw new Error('mixed dependency identities in one Yarn lock stanza');
    const match = lines.find(row => /^  version "/.test(row));
    if (!match) throw new Error('unpinned dependency ' + names[0]);
    const version = /^  version "([^"]+)"$/.exec(match)?.[1];
    if (!version) throw new Error('ambiguous pinned version for ' + names[0]);
    const deps = [];
    let collecting = false;
    for (const row of lines) {
      if (/^  (?:dependencies|optionalDependencies):$/.test(row)) { collecting = true; continue; }
      if (/^  [^\s]/.test(row)) { collecting = false; continue; }
      if (collecting && /^    [^\s]/.test(row)) {
        const m = /^    ("[^"]+"|[^\s]+)\s+"[^"]+"$/.exec(row);
        if (!m) throw new Error('unrecognized dependency edge: ' + row);
        deps.push(m[1].replace(/^"|"$/g, ''));
      }
    }
    rows.push({ name: names[0], version, dependencies: deps });
  }
  if (!rows.length) throw new Error('empty lockfile parsed');
  return rows;
}

function auditLock(source) {
  const entries = parseYarnV1(source);
  const byName = new Map();
  const parents = new Map();
  for (const e of entries) {
    if (!byName.has(e.name)) byName.set(e.name, []);
    byName.get(e.name).push(e);
    for (const child of e.dependencies) {
      if (!parents.has(child)) parents.set(child, new Set());
      parents.get(child).add(e.name + '@' + e.version);
    }
  }
  const findings = [];
  for (const name of TRACKED) {
    const matches = byName.get(name) || [];
    if (!matches.length) {
      findings.push({ name, status: 'not_in_lock', advisory: (PATCHES[name] || RANGES[name] || WITHDRAWN[name]).advisory,
        parents: [], versions: [] });
      continue;
    }
    const versions = [...new Set(matches.map(x => x.version))].sort();
    const directParents = [...(parents.get(name) || [])].sort();
    const policy = PATCHES[name] || RANGES[name] || WITHDRAWN[name];
    let status = 'patched_in_lock';
    if (WITHDRAWN[name]) {
      versions.forEach(versionParts); // Invalid pins still fail closed.
      status = 'advisory_withdrawn';
    } else if (RANGES[name]) {
      const states = versions.map(v => {
        if ((!policy.affectedFrom || compareVersions(v, policy.affectedFrom) >= 0)
            && compareVersions(v, policy.affectedUpTo) <= 0) return 'unpatched_affected';
        const fixed = policy.fixed?.[versionParts(v)[0]];
        if (fixed && compareVersions(v, fixed) >= 0) return 'patched_in_lock';
        return policy.reviewedOutside.includes(v)
          ? 'outside_published_range' : 'requires_advisory_reverification';
      });
      status = states.includes('unpatched_affected') ? 'unpatched_affected'
        : states.includes('requires_advisory_reverification') ? 'requires_advisory_reverification'
          : states.every(s => s === 'patched_in_lock') ? 'patched_in_lock'
            : 'outside_published_range';
    } else {
      status = versions.every(v => {
        const major = versionParts(v)[0];
        const fixed = policy.fixed[major];
        return fixed && compareVersions(v, fixed) >= 0;
      }) ? 'patched_in_lock' : 'patch_required';
    }
    findings.push({ name, status, advisory: policy.advisory, versions, parents: directParents,
      ...(policy.severity ? { severity: policy.severity } : {}) });
  }
  const outstanding = findings.filter(x => !['patched_in_lock', 'not_in_lock', 'advisory_withdrawn', 'outside_published_range'].includes(x.status));
  return {
    schema: 'skeleton.frontend.yarn.security-custody.v1',
    advisory_snapshot: '2026-11-02',
    scope: 'twelve explicitly tracked packages and listed advisories only; not complete Dependabot, live audit, production bundle inventory, or release certification',
    lockfile_entries: entries.length,
    findings, outstanding: outstanding.map(x => x.name),
    release_accepted: outstanding.length === 0,
    automatic_alert_dismissal_authorized: false,
  };
}

if (require.main === module) {
  const flags = process.argv.slice(2);
  if (flags.some(x => x !== '--report-only')) {
    console.error('usage: node scripts/audit-known-yarn-advisories.cjs [--report-only]');
    process.exitCode = 2;
  } else {
    try {
      const lock = fs.readFileSync(path.resolve(__dirname, '..', 'yarn.lock'), 'utf8');
      const result = auditLock(lock);
      console.log(JSON.stringify(result, null, 2));
      if (result.outstanding.length && !flags.includes('--report-only')) process.exitCode = 1;
    } catch (error) {
      console.error('security-custody audit refused: ' + error.message);
      process.exitCode = 2;
    }
  }
}
module.exports = { auditLock, parseYarnV1, compareVersions };

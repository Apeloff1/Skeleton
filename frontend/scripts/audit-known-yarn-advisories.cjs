'use strict';

/** Scoped, offline Yarn v1 security custody; does not suppress Dependabot.
 * Advisory snapshot: 2026-10-16. Default fails while an affected unpatched
 * dependency remains. Use --report-only to generate non-acceptance evidence.
 */
const fs = require('node:fs');
const path = require('node:path');

const PATCHES = Object.freeze({
  'image-size': { fixed: { 2: '2.0.3' }, advisory: 'GHSA-5p2g-fcmc-qvqq / GHSA-w3rx-r6r6-pgpr' },
  'brace-expansion': { fixed: { 1: '1.1.21', 2: '2.1.7', 3: '3.0.9', 5: '5.0.12' }, advisory: 'GHSA-q2hr-2g5m-vwhr' },
  'decode-uri-component': { fixed: { 0: '0.5.0' }, advisory: 'GHSA-vcc3-ghjq-m6fr' },
  'http-cache-semantics': { fixed: { 4: '4.2.1' }, advisory: 'GHSA-ch52-4w7c-c8xp' },
});
const UNPATCHED = Object.freeze({
  braces: { affectedUpTo: '3.0.3', advisory: 'GHSA-vfj7-8cjw-p6xm' },
  'node-forge': { affectedUpTo: '1.4.0', advisory: 'GHSA-86w9-cpqp-85rv' },
});
const TRACKED = Object.freeze([...Object.keys(PATCHES), ...Object.keys(UNPATCHED)]);

function versionParts(value) {
  if (typeof value !== 'string' || !/^\d+\.\d+\.\d+$/.test(value))
    throw new Error('unparseable pinned package version');
  return value.split('.').map(Number);
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
  for (const raw of source.split(/\n\s*\n/)) {
    const lines = raw.split('\n');
    if (!lines[0] || lines[0].startsWith('#')) continue;
    if (!/^[^\s#:][^\n]*:\s*$/.test(lines[0]) && !/^"[^\n]+"(?:,\s*"[^\n]+")*:\s*$/.test(lines[0]))
      throw new Error('unrecognized Yarn lock stanza');
    const header = lines[0].replace(/:\s*$/, '');
    const selectors = header.match(/"[^"]+"|[^,\s]+/g) || [];
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
      findings.push({ name, status: 'not_in_lock', advisory: (PATCHES[name] || UNPATCHED[name]).advisory,
        parents: [], versions: [] });
      continue;
    }
    const versions = [...new Set(matches.map(x => x.version))].sort();
    const directParents = [...(parents.get(name) || [])].sort();
    const policy = PATCHES[name] || UNPATCHED[name];
    let status = 'patched_in_lock';
    if (UNPATCHED[name]) {
      status = versions.every(v => compareVersions(v, policy.affectedUpTo) <= 0)
        ? 'unpatched_affected' : 'requires_advisory_reverification';
    } else {
      status = versions.every(v => {
        const major = versionParts(v)[0];
        const fixed = policy.fixed[major];
        return fixed && compareVersions(v, fixed) >= 0;
      }) ? 'patched_in_lock' : 'patch_required';
    }
    findings.push({ name, status, advisory: policy.advisory, versions, parents: directParents });
  }
  const outstanding = findings.filter(x => !['patched_in_lock', 'not_in_lock'].includes(x.status));
  return {
    schema: 'skeleton.frontend.yarn.security-custody.v1',
    advisory_snapshot: '2026-10-16',
    scope: 'six historically reported packages only; not complete Dependabot or production bundle inventory',
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

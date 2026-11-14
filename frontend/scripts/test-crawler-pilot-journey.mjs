import test from 'node:test';
import { createHash } from 'node:crypto';
import { buildCrawlerEvidenceBundle, CrawlerBundleRefused } from '../src/product/crawlerEvidenceBundle.ts';
import { eligibleForEvidenceBundle, toggleEvidenceBundleSelection } from '../src/product/crawlerBundleSelection.ts';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import {
  EMPTY_PILOT_FORM, PILOT_STAGES, PilotFormError, preparePilotCreate,
  previewPilotScope, derivePilotGates,
} from '../src/features/Jeeves/crawlerPilotFlow.ts';
import { canonicalPilotReceipt, pilotReceiptBody, portablePilotReceipt }
  from '../src/product/crawlerPilotReceipt.ts';
import { bindPilotSnapshot, requireCurrentPilotSnapshot }
  from '../src/features/Jeeves/crawlerPilotContinuity.ts';

const HERE = dirname(fileURLToPath(import.meta.url));
const read = path => readFileSync(resolve(HERE, '..', path), 'utf8');
const validForm = () => ({
  ...EMPTY_PILOT_FORM,
  title: 'Licensed documentation analysis',
  seedText: 'https://www.example.org/guide\nhttps://docs.example.org/latest',
  topicText: 'navigation, accessibility',
  consent: true, rights: true,
});
const command = 'crawler:pilot-create:1234-5678';

test('stage sequence preserves capture, research, human review and receipt', () => {
  assert.deepEqual(PILOT_STAGES.map(x => x.id),
    ['scope', 'capture', 'sources', 'research', 'review', 'receipt']);
  assert.equal(new Set(PILOT_STAGES.map(x => x.id)).size, 6);
});

test('finite authorized capture requires operator consent and rights', () => {
  const prepared = preparePilotCreate(validForm(), command);
  assert.equal(prepared.idempotency_key, command);
  assert.deepEqual(prepared.seeds, [
    'https://www.example.org/guide',
    'https://docs.example.org/latest',
  ]);
  assert.equal(prepared.max_requests, 12);
  assert.equal(prepared.max_documents, 8);
  assert.equal(prepared.max_bytes, 4 * 1048576);
  assert.equal(prepared.max_depth, 1);
  assert.equal(prepared.frontier_strategy, 'balanced');
  assert.equal(prepared.discover_sitemaps, false);
  assert.equal(prepared.consent, true);
  assert.equal(prepared.rights_acknowledged, true);
});

test('input scope preview is not a DNS or robots authority', () => {
  const preview = previewPilotScope('https://docs.example.org/a\nhttps://www.example.org/z');
  assert.deepEqual(preview.hosts, ['docs.example.org', 'www.example.org']);
  assert.equal(preview.requestHostCount, 2);
  assert.equal(preview.seeds.length, 2);
});

test('private hosts, credentials, IPs, plain HTTP, ports and fragments are held', () => {
  const invalid = [
    'http://www.example.org/',
    'https://user:pass@www.example.org/',
    'https://localhost/admin',
    'https://foo.internal/config',
    'https://foo.local/',
    'https://127.0.0.1/',
    'https://[::1]/',
    'https://www.example.org:444/',
    'https://www.example.org/#fragment',
    'https://www.example.org/a\nhttps://www.example.org/a',
    '',
  ];
  for (const seedText of invalid) {
    assert.throws(() => previewPilotScope(seedText), PilotFormError,
      'accepted invalid source: ' + seedText);
  }
});

test('rejects unbounded requests, documents, bytes, depth and inconsistent budgets', () => {
  const invalid = [
    ['maxRequests', '129'], ['maxDocuments', '65'], ['maxMib', '33'],
    ['maxDepth', '4'], ['maxRequests', '-1'], ['maxRequests', 'false'],
    ['maxRequests', '0'], ['maxMib', '0'],
    ['maxRequests', '1'], // fewer requests than 8 documents
  ];
  for (const [key, value] of invalid) {
    assert.throws(() => preparePilotCreate({ ...validForm(), [key]: value }, command),
      PilotFormError, 'accepted invalid budget ' + key + '=' + value);
  }
});

test('denies missing consent, duplicate terms and tampered operation key', () => {
  assert.throws(() => preparePilotCreate({ ...validForm(), rights: false }, command), PilotFormError);
  assert.throws(() => preparePilotCreate({ ...validForm(), consent: false }, command), PilotFormError);
  assert.throws(() => preparePilotCreate({ ...validForm(), topicText: 'bad phrase!' }, command), PilotFormError);
  assert.throws(() => preparePilotCreate(validForm(), 'key with spaces'), PilotFormError);
});

test('source-only progress never becomes release authorization', () => {
  const observation = derivePilotGates({
    readiness: null, session: null, sources: [], atlas: null, canWrite: false,
  });
  assert.equal(observation.length, 7);
  assert.equal(observation.at(-1).id, 'release');
  assert.equal(observation.at(-1).status, 'blocked');
  assert.ok(observation.every(row => row.reason));
});

test('stale captures and absent owner consent never imply research completed', () => {
  const session = {
    session_id: 'owned', title: 'Captured', status: 'paused', version: 2,
    consent_current: false, counters: { requests: 1, documents: 1, bytes: 100 },
  };
  const observation = derivePilotGates({
    readiness: { available: true },
    session,
    sources: [{ freshness: { state: 'withdrawn' } }],
    atlas: null, canWrite: true,
  });
  assert.equal(observation.find(x => x.id === 'capture').status, 'blocked');
  assert.equal(observation.find(x => x.id === 'sources').status, 'blocked');
  assert.equal(observation.find(x => x.id === 'research').status, 'pending');
});

test('canonical pilot receipts sort nested fields and reject invalid numbers', () => {
  const first = canonicalPilotReceipt({ z: [{ b: 1, a: true }], a: { y: 'x', n: null } });
  const second = canonicalPilotReceipt({ a: { n: null, y: 'x' }, z: [{ a: true, b: 1 }] });
  assert.equal(first, second);
  assert.equal(first, '{"a":{"n":null,"y":"x"},"z":[{"a":true,"b":1}]}');
  assert.throws(() => canonicalPilotReceipt({ infinite: Number.POSITIVE_INFINITY }));
  assert.throws(() => canonicalPilotReceipt({ raw: undefined }));
  assert.throws(() => canonicalPilotReceipt({ __proto__: null, f: BigInt(1) }));
});

test('portable receipt omits source bodies and never upgrades release authority', () => {
  const pilot = {
    atlas_digest: 'a'.repeat(64), snapshot_digest: 'b'.repeat(64),
    pilot_status: 'ready_for_human_review',
    qualification_digest: 'f'.repeat(64),
    release_authorized: false, publication_authorized: false,
    training_authorized: false, read_only: true,
    checks: [{ code: 'current_policy', status: 'qualified', next_action: null }],
    external_release_checks: [{ code: 'exact_head_merge_readiness', status: 'not_qualified' }],
  };
  const receipt = {
    pilot_qualification: pilot, atlas_digest: pilot.atlas_digest,
    snapshot_digest: pilot.snapshot_digest,
    source_policy: { digest: 'c'.repeat(64) },
    run_sequence: 4, raw_private_page: 'SHOULD_NOT_LEAK',
  };
  assert.ok(!Object.hasOwn(pilotReceiptBody(pilot), 'qualification_digest'));
  const portable = portablePilotReceipt(receipt);
  assert.ok(!portable.includes('SHOULD_NOT_LEAK'));
  assert.equal(JSON.parse(portable).release_authorized, false);
  assert.equal(JSON.parse(portable).training_authorized, false);
  assert.equal(JSON.parse(portable).publication_authorized, false);
  assert.throws(() => portablePilotReceipt({
    ...receipt, pilot_qualification: { ...pilot, release_authorized: true },
  }));
});

test('real Expo route and client are wired to existing authoritative APIs', () => {
  const route = read('app/dragon-crawler-pilot.tsx');
  const screen = read('src/features/Jeeves/CrawlerReleasePrototype.tsx');
  const client = read('src/product/crawlerClient.ts');
  const panel = read('src/features/Jeeves/CrawlerResearchAtlasPanel.tsx');
  const workspace = read('src/features/Jeeves/CrawlerWorkspace.tsx');
  assert.match(route, /CrawlerReleasePrototype/);
  for (const name of [
    'getCrawlerReadiness', 'listCrawls', 'createCrawl', 'runCrawl',
    'getCrawl', 'listCrawlSources', 'controlCrawl', 'exportCrawlSource',
    'CrawlerResearchAtlasPanel', 'CrawlerSourceLibrary',
    'DragonKnowledgePanel', 'derivePilotGates',
  ]) assert.ok(screen.includes(name), 'missing live product integration: ' + name);
  assert.ok(!screen.includes('fetch('), 'do not bypass trusted transport');
  assert.ok(!screen.includes('new WebSocket'), 'do not invent a network owner');
  assert.match(client, /canonicalPilotReceipt/);
  assert.match(client, /digestStringAsync\(CryptoDigestAlgorithm.SHA256, canonical\)/);
  assert.match(panel, /reportCallback.current\?\.\(data, session.version\)/);
  assert.match(workspace, /Guided research pilot/);
});

const DIGEST = n => n.repeat(64);
const liveSession = () => ({
  session_id: 'owned-session', version: 9, status: 'completed',
  consent_current: true, counters: { requests: 4, documents: 3, bytes: 300 },
});
const liveReport = () => ({
  session_id: 'owned-session', atlas_digest: DIGEST('a'),
  snapshot_digest: DIGEST('b'), run_sequence: 4,
  source_policy: { digest: DIGEST('c') },
  pilot_qualification: {
    source_only: true, read_only: true,
    recheck_mongo_authority_before_any_followup: true,
    atlas_digest: DIGEST('a'), snapshot_digest: DIGEST('b'),
    source_policy_digest: DIGEST('c'),
    qualification_digest: DIGEST('d'), run_sequence: 4,
    release_authorized: false, training_authorized: false,
    publication_authorized: false,
  },
});

test('metadata-only research witness binds a real owned consented revision', () => {
  const current = liveSession();
  const report = liveReport();
  const witness = bindPilotSnapshot(current, report, 9);
  assert.deepEqual(witness, {
    sessionId: current.session_id, sessionVersion: 9,
    atlasDigest: DIGEST('a'), snapshotDigest: DIGEST('b'),
    sourcePolicyDigest: DIGEST('c'), runSequence: 4,
    qualificationDigest: DIGEST('d'),
  });
  assert.ok(Object.isFrozen(witness));
  assert.throws(() => bindPilotSnapshot(current, report, 8));
  assert.throws(() => bindPilotSnapshot(current, report, NaN));
  assert.doesNotThrow(() => requireCurrentPilotSnapshot(
    witness, current, { ...current }, report,
  ));
});

test('late response never upgrades stale, foreign or revoked source metadata', () => {
  const current = liveSession();
  const report = liveReport();
  const wrong = [
    [ { ...current, consent_current: false }, report ],
    [ { ...current, status: 'cancelled' }, report ],
    [ { ...current, version: 10 }, report ],
    [ { ...current, session_id: 'another-owner' }, report ],
    [ current, { ...report, session_id: 'another-owner' } ],
    [ current, { ...report, snapshot_digest: DIGEST('e') } ],
    [ current, { ...report, source_policy: { digest: DIGEST('e') } } ],
    [ current, { ...report, run_sequence: 5 } ],
    [ current, { ...report, pilot_qualification: {
      ...report.pilot_qualification, release_authorized: true,
    } } ],
    [ current, { ...report, pilot_qualification: {
      ...report.pilot_qualification, qualification_digest: 'not-a-hash',
    } } ],
  ];
  for (const [session, response] of wrong) {
    assert.throws(() => bindPilotSnapshot(session, response, 9),
      'A stale or fabricated source snapshot was bound as current');
  }
});

test('share preflight rejects server-side revision, account and consent changes', () => {
  const captured = liveSession(), report = liveReport();
  const witness = bindPilotSnapshot(captured, report, 9);
  for (const live of [
    { ...captured, version: 10 },
    { ...captured, consent_current: false },
    { ...captured, status: 'cancelled' },
    { ...captured, session_id: 'foreign' },
  ]) assert.throws(() => requireCurrentPilotSnapshot(
    witness, captured, live, report,
  ));
  assert.throws(() => requireCurrentPilotSnapshot(
    witness, { ...captured, version: 8 }, captured, report,
  ));
  for (const changed of [
    { ...report, run_sequence: 2 },
    { ...report, atlas_digest: DIGEST('e') },
    { ...report, snapshot_digest: DIGEST('e') },
    { ...report, source_policy: { digest: DIGEST('e') } },
    { ...report, pilot_qualification: {
      ...report.pilot_qualification, qualification_digest: DIGEST('e'),
    } },
  ]) assert.throws(() => requireCurrentPilotSnapshot(
    witness, captured, captured, changed,
  ));
  assert.throws(() => requireCurrentPilotSnapshot(null, captured, captured, report));
  assert.throws(() => requireCurrentPilotSnapshot(witness, null, captured, report));
  assert.throws(() => requireCurrentPilotSnapshot(witness, captured, captured, null));
});

test('user sharing is guarded by a canonical current-revision read, not stale UI state', () => {
  const screen = read('src/features/Jeeves/CrawlerReleasePrototype.tsx');
  assert.match(screen, /const latest = await getCrawl\(current\.session_id, abort\.signal\);/);
  assert.match(screen, /requireCurrentPilotSnapshot\(witness, sessionRef\.current, latest, report\)/);
  assert.match(screen, /shareAbort\.current\?\.abort\(\)/);
  assert.match(screen, /setAtlasWitness\(null\)/);
  assert.match(screen, /current.version !== requestedVersion/);
  assert.match(screen, /await submitPending\(\)/);
  assert.ok(screen.indexOf('requireCurrentPilotSnapshot(witness, sessionRef.current, latest, report);') <
    screen.indexOf("await Share.share({ title: 'Dragon source-only pilot receipt'"));
});

test('real Playwright first-install smoke never mistakes sign-in for crawler authority', () => {
  const source = read('../tests/e2e/app-foundation/dragon-crawler-pilot.spec.mjs');
  assert.match(source, /page.goto\('\/dragon-crawler-pilot'\)/);
  assert.match(source, /gate-email/);
  assert.match(source, /pilot-create/);
  assert.match(source, /toBeDisabled\(\)/);
  assert.match(source, /http:\/\/127\.0\.0\.1\/private/);
  assert.match(source, /crawlerWrites/);
  assert.match(source, /Release authorized: NO/);
});

test('unverifiable owner refresh clears retained evidence before any retry', () => {
  const screen = read('src/features/Jeeves/CrawlerReleasePrototype.tsx');
  const start = screen.indexOf('const reload = useCallback');
  const end = screen.indexOf('const overview = useCallback', start);
  assert.ok(start >= 0 && end > start);
  const reload = screen.slice(start, end);
  const sourceRead = reload.indexOf('const page = await listCrawlSources');
  assert.ok(reload.indexOf('const current = await getCrawl(id, abort.signal)') < sourceRead);
  assert.ok(reload.indexOf('setAtlas(null); setAtlasWitness(null); setReviewDraft(null)') <
    reload.indexOf('const current = await getCrawl(id, abort.signal)'));
  assert.ok(reload.includes('sessionRef.current = null;'));
  assert.ok(reload.includes('setSessions([]);'));
  assert.ok(reload.includes('setSources([]); setSourceCursor(null); setReviewDraft(null);'));
  assert.ok(reload.includes('setReadiness(null);'));
});

test('source withdrawal and new commands revoke any pending receipt share', () => {
  const screen = read('src/features/Jeeves/CrawlerReleasePrototype.tsx');
  assert.match(screen, /shareAbort.current\?\.abort\(\)/);
  assert.match(screen, /before\.consent_current !== value\.consent_current/);
  assert.match(screen, /before\.status !== value\.status/);
  assert.match(screen, /pending\.current \|\| lock\.current \|\| preflightLock\.current \|\| shareLock\.current/);
  assert.match(screen, /policyChanged=\{value => \{[\s\S]*?shareAbort\.current\?\.abort\(\)/);
});

test('authorization refresh destroys retained source text and pending source reads', () => {
  const screen = read('src/features/Jeeves/CrawlerReleasePrototype.tsx');
  const library = read('src/features/Jeeves/CrawlerSourceLibrary.tsx');
  assert.match(screen, /key=\{session\.session_id \+ ':' \+ sourceViewEpoch\}/);
  assert.match(screen, /setSourceViewEpoch\(value => value \+ 1\)/);
  assert.match(screen, /setSourceViewEpoch\(epoch => epoch \+ 1\)/);
  assert.match(library, /const \[page, setPage\] = useState/);
  assert.match(library, /const \[selected, setSelected\] = useState/);
  assert.match(library, /return \(\) => \{ generation\.current\+\+; readRequest\.current\?\.abort\(\)/);
});

test('real editor browser flow preserves public viewer role and requires scoped CI grant', () => {
  const spec = read('../tests/e2e/app-foundation/dragon-crawler-pilot.spec.mjs');
  const qualifier = read('../scripts/qualify_e2e_dragon_editor.py');
  assert.match(spec, /authorizeScopedEditor\(account\.email\)/);
  assert.match(spec, /SKELETON_E2E_OPERATOR_TOKEN_FILE/);
  assert.match(spec, /CI zero-network research/);
  assert.match(spec, /await page\.reload\(\)/);
  assert.match(spec, /toBeDisabled\(\)/);
  assert.match(spec, /toBeEnabled\(\)/);
  assert.match(spec, /actions\[0\]/);
  assert.match(qualifier, /GITHUB_ACTIONS/);
  assert.match(qualifier, /O_NOFOLLOW/);
  assert.match(qualifier, /role.*editor/);
  assert.match(qualifier, /api\/auth\/set-role/);
  assert.ok(!spec.includes("get_header('Authorization')"),
    'admin bearer token must stay out of browser traces');
});


const checksum = text => createHash('sha256').update(text, 'utf8').digest('hex');
const bundleSession = () => ({
  ...liveSession(), status: 'paused', source_count: 2,
  counters: { requests: 2, documents: 2, bytes: 500, failures: 0 },
});
function bundleOptions(overrides = {}) {
  const session = bundleSession();
  const records = Object.fromEntries(['a'.repeat(64), 'b'.repeat(64)].map(source_id =>
    [source_id, {
      source_id, title: 'Untrusted remote title', url: 'https://private.example/doc',
      content_digest: source_id, review_state: 'unreviewed', provenance: {},
      use_policy: { enabled: true, version: 2, max_age_seconds: 3600, changed_at: '2026-11-12T20:00:00Z' },
      freshness: { usable: true, state: 'current', remote_freshness_verified: false },
    }]));
  const sourceContent = id => JSON.stringify({
    ...records[id], text: 'UNTRUSTED_SOURCE_BODY_DO_NOT_EXECUTE',
  });
  return {
    session, sourceIds: Object.keys(records), includeBodies: false,
    checkScope: () => true, sha256: async text => checksum(text),
    getSession: async () => ({ ...session }),
    getSource: async (_sid, id) => records[id],
    exportSource: async (sid, id) => ({
      session_id: sid, source_id: id, content: sourceContent(id),
      filename: id + '.json', media_type: 'application/json',
      content_digest: checksum(sourceContent(id)),
    }),
    ...overrides,
  };
}
test('real owner-scoped multi-source provenance bundle is bounded and contains no source bodies or URLs', async () => {
  const output = await buildCrawlerEvidenceBundle(bundleOptions());
  const payload = JSON.parse(output.content);
  assert.equal(output.content_digest, checksum(output.content));
  assert.equal(payload.schema, 'skeleton.dragon.owner_evidence_bundle.v1');
  assert.equal(payload.mode, 'metadata_only');
  assert.equal(payload.sources.length, 2);
  assert.equal(payload.release_authorized, false);
  assert.equal(payload.publication_authorized, false);
  assert.equal(payload.training_authorized, false);
  assert.ok(!output.content.includes('UNTRUSTED_SOURCE_BODY_DO_NOT_EXECUTE'));
  assert.ok(!output.content.includes('https://private.example/'));
  assert.ok(!output.content.includes('Untrusted remote title'));
  assert.deepEqual(payload.sources.map(x => x.source_id), ['a'.repeat(64), 'b'.repeat(64)]);
});
test('body-mode packet contains actual independently rights-checked source export content and hashes', async () => {
  let readCount = 0, exportCount = 0, sessionCount = 0;
  const original = bundleOptions();
  const result = await buildCrawlerEvidenceBundle(bundleOptions({
    includeBodies: true,
    getSession: async id => { sessionCount++; return original.getSession(id); },
    getSource: async (sid, id) => { readCount++; return original.getSource(sid, id); },
    exportSource: async (sid, id) => { exportCount++; return original.exportSource(sid, id); },
  }));
  const packet = JSON.parse(result.content);
  assert.equal(packet.mode, 'authorized_source_bodies');
  assert.equal(readCount, 4); assert.equal(exportCount, 2); assert.equal(sessionCount, 3);
  assert.ok(result.content.includes('UNTRUSTED_SOURCE_BODY_DO_NOT_EXECUTE'));
  for (const item of packet.sources) {
    assert.equal(checksum(item.authorized_export_body), item.authorized_export_sha256);
    assert.equal(item.authorized_export_media_type, 'application/json');
  }
});
test('stale consent or changed session revision rejects bundle before any export', async () => {
  for (const broken of [
    { consent_current: false }, { version: 10 }, { source_count: 3 },
    { counters: { requests: 3, documents: 2, bytes: 500, failures: 0 } },
  ]) {
    let copies = 0;
    const opts = bundleOptions({
      getSession: async () => ({ ...bundleSession(), ...broken }),
      exportSource: async () => { copies++; throw Error('should not happen'); },
    });
    await assert.rejects(buildCrawlerEvidenceBundle(opts), CrawlerBundleRefused);
    assert.equal(copies, 0);
  }
});
test('one unauthorized, withdrawn, missing or falsified source fails the entire packet', async () => {
  const scenarios = [
    original => ({ ...original, freshness: { ...original.freshness, usable: false, state: 'withdrawn' } }),
    original => ({ ...original, use_policy: { ...original.use_policy, enabled: false } }),
    original => ({ ...original, content_digest: 'not-a-sha' }),
    original => ({ ...original, source_id: 'wrong' }),
  ];
  for (const mutate of scenarios) {
    const baseline = bundleOptions();
    await assert.rejects(buildCrawlerEvidenceBundle({
      ...baseline,
      getSource: async (sid, id) => mutate(await baseline.getSource(sid, id)),
    }), CrawlerBundleRefused);
  }
});
test('bundle blocks account revocation, altered source export checksum and post-export revision race', async () => {
  const base = bundleOptions();
  await assert.rejects(buildCrawlerEvidenceBundle(bundleOptions({ checkScope: () => false })), CrawlerBundleRefused);
  await assert.rejects(buildCrawlerEvidenceBundle(bundleOptions({
    includeBodies: true,
    exportSource: async (sid, id) => ({ ...(await base.exportSource(sid, id)), content_digest: 'f'.repeat(64) }),
  })), CrawlerBundleRefused);
  let reads = 0;
  await assert.rejects(buildCrawlerEvidenceBundle(bundleOptions({
    getSession: async () => ({ ...bundleSession(), version: ++reads === 1 ? 9 : 10 }),
  })), CrawlerBundleRefused);
});
test('enforces max eight sources, rejects duplicate IDs and guards oversized export bodies', async () => {
  await assert.rejects(buildCrawlerEvidenceBundle(bundleOptions({
    sourceIds: Array.from({ length: 9 }, (_, i) => String(i)),
  })), CrawlerBundleRefused);
  await assert.rejects(buildCrawlerEvidenceBundle(bundleOptions({
    sourceIds: ['a'.repeat(64), 'a'.repeat(64)],
  })), CrawlerBundleRefused);
  const base = bundleOptions();
  await assert.rejects(buildCrawlerEvidenceBundle(bundleOptions({
    includeBodies: true,
    exportSource: async (sid, id) => ({
      ...(await base.exportSource(sid, id)),
      content: 'x'.repeat(225001), content_digest: checksum('x'.repeat(225001)),
    }),
  })), CrawlerBundleRefused);
});
test('guided pilot exposes actual audited evidence bundle actions and client-side verification', () => {
  const screen = read('src/features/Jeeves/CrawlerReleasePrototype.tsx');
  const module = read('src/product/crawlerEvidenceBundle.ts');
  assert.match(screen, /dragon-export-metadata-bundle/);
  assert.match(screen, /dragon-export-authorized-bundle/);
  assert.match(screen, /dragon-bundle-source-/);
  assert.match(screen, /dragon-bundle-select-eligible/);
  assert.match(screen, /dragon-bundle-clear-selection/);
  assert.match(screen, /sourceIds: picked/);
  assert.doesNotMatch(screen, /sourceIds: sources\.slice\(0, 8\)/);
  assert.match(screen, /getSource: getCrawlSource/);
  assert.match(screen, /exportSource: exportCrawlSource/);
  assert.match(module, /const after = await options.getSession/);
  assert.match(module, /record\.use_policy\?\.enabled !== true/);
  assert.match(module, /record\.freshness\?\.usable !== true/);
});

test('explicit Dragon evidence selection defaults to no sources and has finite eligible choices', () => {
  const base = bundleOptions();
  const item = base.getSource(undefined, 'a'.repeat(64));
  return item.then(source => {
    assert.equal(eligibleForEvidenceBundle(source), true);
    const first = toggleEvidenceBundleSelection([], source);
    assert.deepEqual(first, [source.source_id]);
    assert.deepEqual(toggleEvidenceBundleSelection(first, source), []);
    assert.equal(eligibleForEvidenceBundle({
      ...source, freshness: {...source.freshness, state: 'withdrawn'},
    }), false);
    assert.throws(() => toggleEvidenceBundleSelection([], {
      ...source, use_policy: {...source.use_policy, enabled: false},
    }));
    assert.throws(() => toggleEvidenceBundleSelection(
      Array.from({length: 8}, (_, i) => String(i)), source,
    ), /eight/);
  });
});
test('authorized JSON must match the separately re-read source identity, policy and content hash', async () => {
  const baseline = bundleOptions();
  const substitutions = [
    original => ({...original, source_id: 'f'.repeat(64)}),
    original => ({...original, content_digest: 'f'.repeat(64)}),
    original => ({...original, use_policy: {...original.use_policy, version: 4}}),
    original => ({...original, use_policy: {...original.use_policy, enabled: false}}),
    original => ({...original, freshness: {...original.freshness, state: 'stale'}}),
    original => ({...original, text: ''}),
  ];
  for (const substitute of substitutions) {
    await assert.rejects(buildCrawlerEvidenceBundle(bundleOptions({
      includeBodies: true,
      exportSource: async (sid, id) => {
        const original = await baseline.exportSource(sid, id);
        const changed = JSON.stringify(substitute(JSON.parse(original.content)));
        return {...original, content: changed, content_digest: checksum(changed)};
      },
    })), CrawlerBundleRefused);
  }
});
test('body export fails closed when previously valid JSON becomes invalid while retaining envelope SHA', async () => {
  const base = bundleOptions();
  await assert.rejects(buildCrawlerEvidenceBundle(bundleOptions({
    includeBodies: true,
    exportSource: async (sid, id) => {
      const original = await base.exportSource(sid, id);
      return {...original, content: '{', content_digest: checksum('{')};
    },
  })), CrawlerBundleRefused);
});

test('final source read refuses permission withdrawal in metadata and body modes', async () => {
  for (const includeBodies of [false, true]) {
    const base = bundleOptions();
    let reads = 0, exports = 0;
    await assert.rejects(buildCrawlerEvidenceBundle(bundleOptions({
      includeBodies,
      getSource: async (sid, id) => {
        const row = await base.getSource(sid, id);
        return ++reads === 3 ? {
          ...row, use_policy: {...row.use_policy, enabled: false, version: 3},
        } : row;
      },
      exportSource: async (sid, id) => {
        exports++;
        return base.exportSource(sid, id);
      },
    })), CrawlerBundleRefused);
    assert.equal(reads, 3);
    assert.equal(exports, includeBodies ? 2 : 0);
  }
});
test('final source policy revalidation rejects digest, policy and freshness drift', async () => {
  const base = bundleOptions();
  const changes = [
    row => ({...row, content_digest: 'c'.repeat(64)}),
    row => ({...row, freshness: {...row.freshness, usable: false}}),
    row => ({...row, freshness: {...row.freshness, state: 'withdrawn'}}),
    row => ({...row, use_policy: {...row.use_policy, changed_at: 'later'}}),
    row => ({...row, use_policy: {...row.use_policy, max_age_seconds: 1}}),
  ];
  for (const change of changes) {
    let reads = 0;
    await assert.rejects(buildCrawlerEvidenceBundle(bundleOptions({
      includeBodies: true,
      getSource: async (sid, id) => {
        const row = await base.getSource(sid, id);
        return ++reads >= 3 ? change(row) : row;
      },
    })), CrawlerBundleRefused);
  }
});
test('final consent read rejects revocation during final source authorization', async () => {
  let reads = 0;
  await assert.rejects(buildCrawlerEvidenceBundle(bundleOptions({
    includeBodies: true,
    getSession: async () => ({
      ...bundleSession(), consent_current: ++reads !== 3,
    }),
  })), CrawlerBundleRefused);
  assert.equal(reads, 3);
});
test('source revalidation retains deterministic content, SHA, and non-release policy', async () => {
  const one = await buildCrawlerEvidenceBundle(bundleOptions({includeBodies: true}));
  const two = await buildCrawlerEvidenceBundle(bundleOptions({includeBodies: true}));
  assert.equal(one.content_digest, two.content_digest);
  const packet = JSON.parse(one.content);
  assert.equal(packet.source_count, 2);
  assert.equal(packet.release_authorized, false);
  assert.equal(packet.publication_authorized, false);
  assert.equal(packet.training_authorized, false);
});

import test from 'node:test';
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
  assert.match(panel, /reportCallback.current\?\.\(data\)/);
  assert.match(workspace, /Guided research pilot/);
});

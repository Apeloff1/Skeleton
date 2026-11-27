const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const crypto = require('node:crypto');
const { execFileSync } = require('node:child_process');
const ts = require('typescript');
const { assert, load, deferred, tick } = require('./helpers.cjs');
const draftHelpers = load('../journeys/journeyDraft');

const repository = path.resolve(__dirname, '../../..');
// Fixtures come from the canonical owner, including its actual option DTOs and fingerprints.
const fixtures = JSON.parse(execFileSync('python3', ['-c', `
import json
from skeleton.contracts.ai_workflows import workflow_journey_catalog, prepare_workflow_draft, validate_workflow_artifact
request = {"journey_id":"research","goal":"Compare the supplied observation · 海 🌱","options":{"focus":"comparison","max_claims":3},"source_refs":[{"id":"source-1","label":"Selected observation","locator":"https://example.test/chosen","excerpt":"Observed text only."}]}
def make(req):
    draft = prepare_workflow_draft(req)
    artifact = {"schema_version":"skeleton.ai.workflow_artifact.v1","journey_id":"research","request_digest":draft["request_digest"],"title":"Evidence comparison","summary":"A cautious summary.","claims":[{"text":"The observation reports a result.","source_ids":["source-1"],"confidence":"supported"}],"open_questions":["Does it reproduce?"]}
    return draft, artifact, validate_workflow_artifact({**req,"artifact":artifact})
draft, artifact, preview = make(request)
other_draft, other_artifact, other_preview = make({**request,"goal":"A different request"})
print(json.dumps({"catalog":workflow_journey_catalog(),"request":request,"draft":draft,"artifact":artifact,"preview":preview,"other_draft":other_draft,"other_artifact":other_artifact,"other_preview":other_preview},ensure_ascii=False))
`], { cwd: repository, encoding: 'utf8', maxBuffer: 1024 * 1024 }));
const clone = value => JSON.parse(JSON.stringify(value));
const digest = value => crypto.createHash('sha256').update(draftHelpers.canonicalJourneyJSON(value), 'utf8').digest('hex');
function rehash(value, field) { delete value[field]; value[field] = digest(value); return value; }

function client(overrides = {}) {
  const auth = { token: 'private-token-A', epoch: 1 };
  const calls = [];
  const responses = {
    '/api/ai/workflow-journeys': { schema_version: 'skeleton.ai.workflow_journeys.v1', actor_id: 'owner@example.test', tenant_id: 'tenant-A', catalog: clone(fixtures.catalog) },
    '/api/ai/workflow-drafts': { schema_version: 'skeleton.ai.workflow_draft_response.v1', actor_id: 'owner@example.test', tenant_id: 'tenant-A', draft: clone(fixtures.draft) },
    '/api/ai/workflow-artifacts': { schema_version: 'skeleton.ai.workflow_artifact_response.v1', actor_id: 'owner@example.test', tenant_id: 'tenant-A', preview: clone(fixtures.preview) },
  };
  const invoke = async (method, route, body, options) => {
    calls.push({ method, route, body: body === undefined ? undefined : clone(body), options });
    if (overrides.beforeResponse) await overrides.beforeResponse(route);
    return { ok: true, data: route === '/api/auth/me'
      ? { authenticated: true, user: { email: 'owner@example.test', tenant_id: 'tenant-A' } }
      : responses[route] };
  };
  const api = { get: (route, options) => invoke('GET', route, undefined, options), post: (route, body, options) => invoke('POST', route, body, options) };
  const filename = path.join(repository, 'frontend/src/product/aiJourneyClient.ts');
  const code = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS }, fileName: filename,
  }).outputText;
  const module = { exports: {} };
  vm.runInNewContext(code, { module, exports: module.exports, require(name) {
    if (name === '../auth/gameforgeAuth') return { getAuthToken: () => auth.token, getAuthEpoch: () => auth.epoch,
      initializeStoredToken: async () => { if (overrides.initialize) await overrides.initialize(auth); },
      authHeaders: () => ({ Authorization: 'Bearer ' + auth.token }) };
    if (name === '../utils/apiClient') return { default: api };
    if (name === './chatErrors') return { chatApiError: (_result, message) => new Error(message) };
    if (name === '../features/Jeeves/journeys/journeyDraft') return draftHelpers;
    if (name === 'expo-crypto') return { CryptoDigestAlgorithm: { SHA256: 'SHA-256' }, digestStringAsync: async (algorithm, text) => {
      assert.equal(algorithm, 'SHA-256');
      if (overrides.beforeDigest) await overrides.beforeDigest();
      return crypto.createHash('sha256').update(text, 'utf8').digest('hex');
    } };
    throw new Error('Unexpected client dependency: ' + name);
  } }, { filename });
  return { api: module.exports, auth, calls, responses };
}

test('cold stored-token hydration precedes workflow scope and authenticated transport', async () => {
  const h = client({ initialize: async auth => { auth.token = 'private-token-A'; } });
  h.auth.token = '';
  const catalog = await h.api.getJourneyCatalog();
  assert.equal(catalog.journeys.length, 5);
  assert.equal(h.calls.length, 2);
  assert.ok(h.calls.every(call => call.options.headers.Authorization === 'Bearer private-token-A'));
});

test('account changes or closing during token hydration cannot issue a workflow request', async () => {
  for (const stop of ['account', 'abort']) {
    const gate = deferred(); let started = false;
    const h = client({ initialize: async () => { started = true; await gate.promise; } });
    const controller = new AbortController();
    const pending = h.api.getJourneyCatalog(controller.signal);
    for (let attempt = 0; !started && attempt < 100; attempt++) await tick();
    assert.equal(started, true);
    if (stop === 'account') h.auth.epoch += 1; else controller.abort();
    gate.resolve();
    await assert.rejects(pending, /account changed|review was closed/);
    assert.equal(h.calls.length, 0);
  }
});

test('actual server catalog accepts choice/integer DTOs and uses authenticated bounded transport', async () => {
  const h = client();
  const catalog = await h.api.getJourneyCatalog();
  assert.equal(catalog.journeys.length, 5);
  assert.equal(catalog.journeys[0].options.focus.type, 'choice');
  assert.deepEqual(catalog.journeys[0].options.focus.choices, ['overview', 'comparison', 'decision']);
  assert.equal(catalog.execution_authorized, false);
  assert.equal(h.calls[0].route, '/api/auth/me');
  for (const call of h.calls) {
    assert.equal(call.options.headers.Authorization, 'Bearer private-token-A');
    assert.equal(call.options.retries, 0); assert.equal(call.options.timeoutMs, 15000);
    assert.equal(call.options.maxResponseChars, 128 * 1024);
  }
});

test('unsupported choice shapes and changed catalog fingerprints are rejected', async () => {
  const shape = client(); const catalog = shape.responses['/api/ai/workflow-journeys'].catalog;
  catalog.journeys[0].options.focus.choices = 'overview'; rehash(catalog, 'catalog_digest');
  await assert.rejects(shape.api.getJourneyCatalog(), /option list is invalid/);
  const tamper = client(); tamper.responses['/api/ai/workflow-journeys'].catalog.journeys[0].title = 'Changed title';
  await assert.rejects(tamper.api.getJourneyCatalog(), /fingerprint/);
});

test('prepared request preserves exactly the selected source and normalized options', async () => {
  const h = client(); const selected = clone(fixtures.request);
  const unselected = { id: 'not-selected', label: 'Private excluded reference', locator: 'file:///private', excerpt: 'Must not be transmitted' };
  const prepared = await h.api.prepareJourneyDraft(selected);
  const post = h.calls.find(call => call.method === 'POST');
  assert.deepEqual(post.body.source_refs, selected.source_refs);
  assert.deepEqual(prepared.request.source_refs, selected.source_refs);
  assert.equal(JSON.stringify(post.body).includes(unselected.excerpt), false);
  assert.equal(prepared.request_digest, digest(prepared.request));
  assert.equal(prepared.execution_authorized, false);
  assert.equal(h.calls.filter(call => call.method === 'POST').length, 1);
});

test('self-consistent substituted options, sources and draft digests cannot replace the submitted request', async () => {
  for (const mutate of [
    request => { request.options.focus = 'decision'; },
    request => { request.source_refs[0].excerpt = 'Substituted source'; },
  ]) {
    const h = client(); const draft = h.responses['/api/ai/workflow-drafts'].draft;
    mutate(draft.request); draft.request_digest = digest(draft.request);
    draft.prompt = draftHelpers.REQUEST_MARKER + draftHelpers.canonicalJourneyJSON({ request: draft.request, request_digest: draft.request_digest });
    rehash(draft, 'draft_digest');
    await assert.rejects(h.api.prepareJourneyDraft(clone(fixtures.request)), /differs from your selected content or options/);
  }
  const wrongDigest = client(); wrongDigest.responses['/api/ai/workflow-drafts'].draft.draft_digest = '0'.repeat(64);
  await assert.rejects(wrongDigest.api.prepareJourneyDraft(clone(fixtures.request)), /fingerprint/);
});

test('foreign actor and tenant responses fail closed on every preview surface', async () => {
  const operations = [
    ['workflow-journeys', h => h.api.getJourneyCatalog()],
    ['workflow-drafts', h => h.api.prepareJourneyDraft(clone(fixtures.request))],
    ['workflow-artifacts', h => h.api.validateJourneyArtifact(clone(fixtures.request), clone(fixtures.artifact))],
  ];
  for (const [route, run] of operations) for (const field of ['actor_id', 'tenant_id']) {
    const h = client(); h.responses['/api/ai/' + route][field] = 'another-owner';
    await assert.rejects(run(h), /does not belong to the current account/);
  }
});

test('account or epoch change while network or digest work is pending refuses stale results', async () => {
  for (const stage of ['network', 'digest']) for (const field of ['token', 'epoch']) {
    const gate = deferred(); let started = false;
    const h = client(stage === 'network' ? { beforeResponse: async route => {
      if (route === '/api/ai/workflow-journeys') { started = true; await gate.promise; }
    } } : { beforeDigest: async () => { started = true; await gate.promise; } });
    const pending = h.api.getJourneyCatalog();
    for (let attempt = 0; !started && attempt < 100; attempt++) await tick();
    assert.equal(started, true, 'the actual client reached the gated operation');
    h.auth[field] = field === 'token' ? 'private-token-B' : 2;
    gate.resolve();
    await assert.rejects(pending, /account changed|review was closed/);
  }
});

test('an aborted draft review cannot return a usable preview', async () => {
  const gate = deferred(); let started = false;
  const h = client({ beforeResponse: async route => { if (route.endsWith('/workflow-drafts')) { started = true; await gate.promise; } } });
  const controller = new AbortController();
  const pending = h.api.prepareJourneyDraft(clone(fixtures.request), controller.signal);
  for (let attempt = 0; !started && attempt < 100; attempt++) await tick();
  assert.equal(started, true, 'the actual client reached the draft request');
  controller.abort(); gate.resolve();
  await assert.rejects(pending, /review was closed/);
});

test('artifact bytes and request identity must match their fingerprints and result binding', async () => {
  const altered = client(); altered.responses['/api/ai/workflow-artifacts'].preview.artifact.summary = 'Changed after validation';
  await assert.rejects(altered.api.validateJourneyArtifact(clone(fixtures.request), clone(fixtures.artifact)), /fingerprint/);
  const h = client(); h.responses['/api/ai/workflow-artifacts'].preview = clone(fixtures.other_preview);
  await assert.rejects(h.api.validateJourneyArtifact(clone(fixtures.request), clone(fixtures.artifact)), /fingerprint|different.*request/);
  assert.throws(() => draftHelpers.readJourneyArtifact(JSON.stringify(fixtures.other_preview.artifact), fixtures.request, fixtures.draft.request_digest), /does not match this journey request/);
});

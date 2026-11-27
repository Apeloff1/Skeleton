const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const ts = require('typescript');

const root = path.resolve(__dirname, '../..');
const clone = value => JSON.parse(JSON.stringify(value));
function compiled(relative) {
  const filename = path.join(root, relative);
  return ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    fileName: filename, compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
  }).outputText;
}
function evaluate(code, requireDependency) {
  const fixture = { exports: {} };
  // A shared realm preserves the real Error and plain-object semantics. The
  // application helper and error decoder execute unchanged, without Expo SDKs.
  new Function('module', 'exports', 'require', code)(fixture, fixture.exports, requireDependency);
  return fixture.exports;
}
const noDependency = name => { throw new Error('Unexpected pure dependency: ' + name); };
const queue = evaluate(compiled('src/features/Jeeves/forgeParameters/forgeQueuedSave.ts'), noDependency);
const errors = evaluate(compiled('src/product/chatErrors.ts'), noDependency);
const clientCode = compiled('src/product/gameFrontierAuthoringClient.ts');

// Use the actual operation catalogue; fixture success does not invent editor
// actions or imply that any backend/model/native operation was executed here.
const panelPath = path.join(root, 'src/features/Jeeves/GameFrontierAuthoringPanel.tsx');
const panelSource = fs.readFileSync(panelPath, 'utf8');
const panelTree = ts.createSourceFile(panelPath, panelSource, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
let groupSource;
function findGroups(node) {
  if (ts.isVariableDeclaration(node) && node.name.getText(panelTree) === 'GROUPS') groupSource = node.initializer.getText(panelTree);
  ts.forEachChild(node, findGroups);
}
findGroups(panelTree);
assert.ok(groupSource, 'The canonical panel operation catalogue must exist.');
const catalogue = new Function('return (' + groupSource + ');')().flatMap(group => group.actions);
assert.equal(catalogue.length, 500);
assert.equal(new Set(catalogue).size, 500);

const SOURCE = 'a'.repeat(64), CANDIDATE = 'b'.repeat(64);
const inputSteps = () => [{ action: 'tile_set', parameters: { layer: 'ground', x: 2, y: 3, tile: 2 } }];
function document(overrides = {}) {
  return { schema: 'skeleton.game.frontier_studio_document.v1', project_id: 'project-one', expected_version: 3,
    source_sha256: SOURCE, layers: [{ id: 'ground', size: [16, 16], tile_count: 256, palette_size: 3, elevation_m: 0 }],
    prefab_count: 0, placed_actor_count: 0, authored_event_count: 0, quest_count: 0, music_cue_count: 0,
    prefab_catalog: [], actor_catalog: [], quest_catalog: [], action_catalog: catalogue.slice(), already_saved: true,
    recipe_catalog_count: 4999999999500, catalog_total: 5000000000000, recipe_search_required: true,
    classic_recipe_count: 4500, expanded_recipe_count: 45000, directed_recipe_count: 450000,
    final_recipe_count: 4500000, worldline_recipe_count: 45000000, phase_recipe_count: 450000000,
    campaign_recipe_count: 4500000000, chronicle_recipe_count: 45000000000, epoch_recipe_count: 450000000000,
    continuity_recipe_count: 4500000000000, ...overrides };
}
function result(call, options = {}) {
  const preview = call.method === 'POST';
  const source = call.body.expected_sha256;
  const candidate = options.candidate || CANDIDATE;
  const base = document();
  const { expected_version, already_saved, ...summary } = base;
  let before = source;
  const changes = call.body.steps.map((step, index) => {
    const after = index === call.body.steps.length - 1 ? candidate
      : crypto.createHash('sha256').update('fixture-intermediate-' + index).digest('hex');
    const change = { index, operation: step.action, before_sha256: before, after_sha256: after, changed: before !== after };
    before = after;
    return change;
  });
  const value = {
    schema: preview ? 'skeleton.game.frontier_studio_preview.v1' : 'skeleton.game.frontier_studio_committed.v1',
    persisted: !preview,
    source_sha256: preview ? source : candidate,
    summary: { ...summary, schema: 'skeleton.forge.frontier_authoring_summary.v1', source_sha256: candidate, candidate_only: true },
    batch_receipt: { schema: 'skeleton.forge.frontier_authoring_batch.v1', project_id: 'project-one',
      source_sha256: source, candidate_sha256: candidate, persisted: false,
      action_count: call.body.steps.length, actually_changed: source !== candidate,
      receipt_sha256: 'c'.repeat(64), changes },
  };
  if (preview) value.candidate_sha256 = candidate;
  else Object.assign(value, { project_id: 'project-one', expected_version: call.body.expected_version + 1,
    request_id: call.body.idempotency_key, origin_request_digest: 'd'.repeat(64),
    original_source_sha256: source, head_version: options.headVersion || call.body.expected_version + 1,
    replayed: options.replayed || false });
  return value;
}
const success = data => ({ ok: true, status: 200, data, error: null, rid: 'fixture-response' });
function deferred() { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; }

function client(overrides = {}) {
  const auth = { token: 'fixture-session-a', epoch: 7, ...(overrides.auth || {}) };
  const calls = [], keys = [], events = [];
  const invoke = async (method, route, body, options) => {
    const call = { method, route, body: clone(body), options: { ...options, headers: { ...options.headers } } };
    calls.push(call); events.push('http');
    if (overrides.beforeResponse) await overrides.beforeResponse(call, calls.length);
    return overrides.respond ? await overrides.respond(call, calls.length) : success(result(call));
  };
  const api = { patch: (route, body, options) => invoke('PATCH', route, body, options),
    post: (route, body, options) => invoke('POST', route, body, options),
    get: () => { throw new Error('Save boundary unexpectedly issued a GET.'); } };
  const actual = evaluate(clientCode, name => {
    if (name === '../utils/apiClient') return { default: api };
    if (name === '../auth/gameforgeAuth') return {
      authHeaders: () => auth.token ? { Authorization: 'Bearer ' + auth.token } : {},
      getAuthEpoch: () => auth.epoch, getAuthToken: () => auth.token,
      initializeStoredToken: async () => { events.push('initialize'); if (overrides.initialize) await overrides.initialize(auth); },
    };
    if (name === './chatErrors') return errors;
    if (name === './gameLearningClient') return { learningRequestKey: prefix => {
      const key = prefix + '-fixture-' + (keys.length + 1); keys.push(key); events.push('key'); return key;
    } };
    if (name === '../features/Jeeves/forgeParameters/forgeQueuedSave') return queue;
    throw new Error('Unexpected client dependency: ' + name);
  });
  return { api: actual, auth, calls, keys, events };
}
async function rejected(h, pending, preDispatch) {
  await assert.rejects(pending, error => {
    assert.ok(error instanceof h.api.ForgeEditError);
    assert.ok(error instanceof errors.ChatClientError);
    assert.equal(error.preDispatch, preDispatch);
    return true;
  });
}

test('explicit save identity, source and steps are captured before token initialization awaits', async () => {
  const gate = deferred();
  const h = client({ initialize: () => gate.promise });
  const doc = document(), steps = inputSteps();
  const pending = h.api.editForge('project-one', doc, steps, false, 'original-stable-key');
  assert.equal(h.calls.length, 0);
  assert.equal(h.keys.length, 0);
  doc.expected_version = 99; doc.source_sha256 = 'e'.repeat(64); doc.action_catalog.length = 0;
  steps[0].parameters.x = 9; steps.push({ action: 'tile_set', parameters: { layer: 'ground', x: 7, y: 7, tile: 1 } });
  gate.resolve();
  const saved = await pending;
  assert.equal(saved.expected_version, 4);
  assert.deepEqual(h.calls[0].body, { expected_version: 3, expected_sha256: SOURCE,
    idempotency_key: 'original-stable-key', steps: inputSteps() });
  assert.equal(h.calls[0].options.idempotencyKey, 'original-stable-key');
  assert.equal(h.calls[0].options.retries, 0);
});

test('legacy four-argument callers allocate exactly one key before hydration and preserve the closed body', async () => {
  const gate = deferred();
  const h = client({ initialize: () => gate.promise });
  const pending = h.api.editForge('project-one', document(), inputSteps(), false);
  assert.equal(h.keys.length, 1);
  assert.deepEqual(h.events, ['key', 'initialize']);
  gate.resolve(); await pending;
  assert.equal(h.keys.length, 1);
  assert.equal(h.calls[0].body.idempotency_key, h.keys[0]);
  assert.equal(h.calls[0].options.idempotencyKey, h.keys[0]);
  assert.deepEqual(Object.keys(h.calls[0].body).sort(), ['expected_sha256', 'expected_version', 'idempotency_key', 'steps']);
});

test('unknown acknowledgement never retries automatically; an explicit replay uses the exact original request', async () => {
  const h = client({ respond: (call, attempt) => attempt === 1
    ? { ok: false, status: 0, data: null, error: 'timeout', rid: null }
    : success(result(call, { replayed: true, headVersion: 11 })) });
  await rejected(h, h.api.editForge('project-one', document(), inputSteps(), false, 'retry-original'), false);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(h.calls.length, 1);
  assert.equal(h.calls[0].options.retries, 0);
  const recovered = await h.api.editForge('project-one', document(), inputSteps(), false, 'retry-original');
  assert.equal(h.calls.length, 2);
  assert.deepEqual(h.calls[1].body, h.calls[0].body);
  assert.equal(recovered.request_id, 'retry-original');
  assert.equal(recovered.expected_version, 4);
  assert.equal(recovered.head_version, 11);
  assert.equal(recovered.replayed, true);
});

test('only exact HTTP four-hundred pre-dispatch proofs classify server failure as definitive', async () => {
  for (const status of [400, 409, 422]) {
    const h = client({ respond: () => ({ ok: false, status, data: { detail: {
      code: 'frontier_pre_dispatch', message: 'Rejected before revision preparation.' } }, error: null, rid: 'fixture-denied' }) });
    await rejected(h, h.api.editForge('project-one', document(), inputSteps(), false, 'proof'), true);
    assert.equal(h.calls.length, 1);
  }
  for (const [status, code] of [[400, 'invalid_request'], [401, 'authentication_required'],
    [403, 'editor_required'], [404, 'not_found'], [409, 'studio_source_conflict'],
    [422, 'invalid_source'], [500, 'frontier_pre_dispatch'], [0, 'frontier_pre_dispatch']]) {
    const h = client({ respond: () => ({ ok: false, status, data: { detail: { code, message: 'Unconfirmed.' } }, error: null, rid: null }) });
    await rejected(h, h.api.editForge('project-one', document(), inputSteps(), false, 'unconfirmed'), false);
    assert.equal(h.calls.length, 1);
  }
});

test('transport rejection remains uncertain and retains actual safe error typing', async () => {
  const h = client({ beforeResponse: () => { throw new Error('Fixture socket closed after send'); } });
  await rejected(h, h.api.editForge('project-one', document(), inputSteps(), false, 'socket-ack'), false);
  assert.equal(h.calls.length, 1);
});

test('an HTTP success without a complete receipt remains uncertain rather than confirming or resubmitting', async () => {
  for (const payload of [null, [], 'unexpected HTML-like response', 0, {}]) {
    const h = client({ respond: () => success(payload) });
    await rejected(h, h.api.editForge('project-one', document(), inputSteps(), false, 'missing-receipt'), false);
    assert.equal(h.calls.length, 1);
    assert.equal(h.calls[0].options.retries, 0);
  }
});

test('unbound commit identities, versions and origin fields never become successful acknowledgements', async () => {
  const mutations = [
    value => { value.schema = 'wrong'; }, value => { value.persisted = false; },
    value => { value.project_id = 'another-project'; }, value => { value.request_id = 'another-key'; },
    value => { value.original_source_sha256 = 'e'.repeat(64); },
    value => { value.expected_version = 5; }, value => { value.head_version = 3; },
    value => { value.head_version = 4.5; }, value => { value.head_version = Infinity; },
    value => { value.replayed = 'true'; }, value => { delete value.origin_request_digest; },
    value => { value.origin_request_digest = 'not-a-digest'; },
    value => { value.source_sha256 = SOURCE; }, value => { value.native_engine_executed = true; },
    value => { value.release_certified = true; }, value => { value.native_engine_executed = 'true'; },
    value => { value.release_certified = 1; }, value => { value.release_certified = null; },
  ];
  for (const mutate of mutations) {
    const h = client({ respond: call => { const value = result(call); mutate(value); return success(value); } });
    await rejected(h, h.api.editForge('project-one', document(), inputSteps(), false, 'bound-key'), false);
    assert.equal(h.calls.length, 1);
  }
});

test('candidate summaries and every batch hash-chain edge bind the original requested operations', async () => {
  const mutations = [
    value => { value.summary = null; }, value => { value.summary.schema = 'wrong'; },
    value => { value.summary.candidate_only = false; }, value => { value.summary.project_id = 'another'; },
    value => { value.summary.source_sha256 = SOURCE; }, value => { value.summary.action_catalog.pop(); },
    value => { value.summary.native_engine_executed = 'true'; }, value => { value.summary.release_certified = null; },
    value => { value.batch_receipt = null; }, value => { value.batch_receipt.schema = 'wrong'; },
    value => { value.batch_receipt.project_id = 'another'; }, value => { value.batch_receipt.source_sha256 = CANDIDATE; },
    value => { value.batch_receipt.candidate_sha256 = SOURCE; }, value => { value.batch_receipt.persisted = true; },
    value => { value.batch_receipt.action_count = 1; }, value => { value.batch_receipt.actually_changed = false; },
    value => { value.batch_receipt.receipt_sha256 = 'invalid'; }, value => { value.batch_receipt.changes.pop(); },
    value => { value.batch_receipt.changes[0] = null; }, value => { value.batch_receipt.changes[0].index = 1; },
    value => { value.batch_receipt.changes[0].operation = 'different-operation'; },
    value => { value.batch_receipt.changes[0].before_sha256 = CANDIDATE; },
    value => { value.batch_receipt.changes[0].after_sha256 = 'invalid'; },
    value => { value.batch_receipt.changes[0].changed = false; },
    value => { value.batch_receipt.changes[1].before_sha256 = SOURCE; },
    value => { value.batch_receipt.changes[1].after_sha256 = SOURCE; },
  ];
  const steps = [...inputSteps(), { action: 'tile_set', parameters: { layer: 'ground', x: 5, y: 5, tile: 1 } }];
  for (const mutate of mutations) {
    const h = client({ respond: call => { const value = result(call); mutate(value); return success(value); } });
    await rejected(h, h.api.editForge('project-one', document(), steps, false, 'chain-key'), false);
    assert.equal(h.calls.length, 1);
  }
});

test('preview uses the pure endpoint and rejects committed or foreign source evidence', async () => {
  const h = client();
  const preview = await h.api.editForge('project-one', document(), inputSteps(), true, 'preview-key');
  assert.equal(preview.persisted, false);
  assert.equal(h.calls[0].method, 'POST');
  assert.equal(h.calls[0].route, '/api/game-frontier-authoring/projects/project-one/edits/preview');
  for (const mutate of [value => { value.persisted = true; }, value => { value.source_sha256 = CANDIDATE; },
    value => { value.schema = 'skeleton.game.frontier_studio_committed.v1'; }]) {
    const bad = client({ respond: call => { const value = result(call); mutate(value); return success(value); } });
    await rejected(bad, bad.api.editForge('project-one', document(), inputSteps(), true, 'preview-bound'), false);
  }
});

test('optional source flags accept only explicit false and origin digests remain opaque server values', async () => {
  const h = client({ respond: call => {
    const value = result(call);
    value.native_engine_executed = false; value.release_certified = false;
    value.summary.native_engine_executed = false; value.summary.release_certified = false;
    value.origin_request_digest = 'f'.repeat(64);
    return success(value);
  } });
  const saved = await h.api.editForge('project-one', document(), inputSteps(), false, 'source-only');
  assert.equal(saved.origin_request_digest, 'f'.repeat(64));
  assert.equal(saved.native_engine_executed, false);
  assert.equal(saved.release_certified, false);
});

test('unchanged previews remain useful while even internally consistent unchanged commit receipts are refused', async () => {
  const h = client({ respond: call => success(result(call, { candidate: SOURCE })) });
  const preview = await h.api.editForge('project-one', document(), inputSteps(), true, 'unchanged-preview');
  assert.equal(preview.batch_receipt.actually_changed, false);
  assert.equal(preview.candidate_sha256, SOURCE);
  await rejected(h, h.api.editForge('project-one', document(), inputSteps(), false, 'unchanged-save'), false);
  assert.equal(h.calls.length, 2);
});

test('cold token hydration finishes before authentication headers and response scope are captured', async () => {
  const h = client({ auth: { token: '' }, initialize: async auth => { auth.token = 'fixture-loaded-token'; } });
  await h.api.editForge('project-one', document(), inputSteps(), false, 'cold-start');
  assert.equal(h.calls[0].options.headers.Authorization, 'Bearer fixture-loaded-token');
  assert.deepEqual(h.events, ['initialize', 'http']);
});

test('account rotation before send is definitive, while late token or epoch rotation cannot acknowledge a save', async () => {
  const before = client({ initialize: async auth => { auth.token = 'fixture-session-b'; auth.epoch += 1; } });
  await rejected(before, before.api.editForge('project-one', document(), inputSteps(), false, 'before-send'), true);
  assert.equal(before.calls.length, 0);
  for (const field of ['token', 'epoch']) {
    const gate = deferred(); let arrived = false;
    const h = client({ beforeResponse: async () => { arrived = true; await gate.promise; } });
    const pending = h.api.editForge('project-one', document(), inputSteps(), false, 'late-account');
    for (let attempt = 0; !arrived && attempt < 20; attempt++) await new Promise(resolve => setImmediate(resolve));
    assert.equal(arrived, true);
    h.auth[field] = field === 'token' ? 'fixture-session-b' : 8;
    gate.resolve();
    await rejected(h, pending, false);
    assert.equal(h.calls.length, 1);
  }
});

test('session-local queue IDs are absent from the actual closed client request', async () => {
  const locals = [queue.queueForgeStep('local-private-step', inputSteps()[0])];
  const h = client();
  await h.api.editForge('project-one', document(), queue.forgeQueueWireSteps(locals), false, 'wire-key');
  assert.deepEqual(h.calls[0].body.steps, inputSteps());
  assert.equal(JSON.stringify(h.calls[0].body).includes('local-private-step'), false);
  assert.deepEqual(Object.keys(h.calls[0].body.steps[0]), ['action', 'parameters']);
});

test('local malformed JSON data, source mismatches and mutating getters cannot issue HTTP', async () => {
  let getterCalls = 0;
  const cyclic = {}; cyclic.self = cyclic;
  const accessor = Object.defineProperty({}, 'x', { enumerable: true, get() { getterCalls += 1; return 2; } });
  const badSteps = [[], [{ action: 'not-a-real-action', parameters: {} }],
    [{ action: 'tile_set', parameters: { x: NaN } }],
    [{ action: 'tile_set', parameters: cyclic }], [{ action: 'tile_set', parameters: accessor }]];
  for (const steps of badSteps) {
    const h = client();
    await rejected(h, h.api.editForge('project-one', document(), steps, false, 'local-reject'), true);
    assert.equal(h.calls.length, 0);
  }
  assert.equal(getterCalls, 0);
  const h = client();
  await rejected(h, h.api.editForge('project-one', document({ project_id: 'foreign' }), inputSteps(), false, 'mismatch'), true);
  assert.equal(h.calls.length, 0);
});

test('document, catalogue and step-array accessors cannot execute before the local HTTP guard', async () => {
  let calls = 0;
  const indexed = inputSteps();
  Object.defineProperty(indexed, '0', { enumerable: true, get() { calls += 1; return inputSteps()[0]; } });
  const source = document();
  Object.defineProperty(source, 'source_sha256', { enumerable: true, get() { calls += 1; return SOURCE; } });
  const catalogue = document();
  Object.defineProperty(catalogue.action_catalog, '0', { enumerable: true, get() { calls += 1; return 'tile_set'; } });
  for (const [doc, steps] of [[document(), indexed], [source, inputSteps()], [catalogue, inputSteps()]]) {
    const h = client();
    await rejected(h, h.api.editForge('project-one', doc, steps, false, 'local-envelope'), true);
    assert.equal(h.calls.length, 0);
  }
  assert.equal(calls, 0);
});

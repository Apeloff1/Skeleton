'use strict';
// Exercise actual policy, transport, persistence and control code with local seams.
const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const { compileFunction } = require('node:vm');
const ts = require('typescript');
const ROOT = path.resolve(__dirname, '..');
function load(relative, imports = {}) {
  const output = ts.transpileModule(fs.readFileSync(path.join(ROOT, relative), 'utf8'), {
    fileName: relative, reportDiagnostics: true,
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
  });
  assert.equal(output.diagnostics.length, 0, relative + ' must compile');
  const module = { exports: {} };
  compileFunction(output.outputText, ['require', 'module', 'exports'])(id => {
    assert.ok(Object.hasOwn(imports, id), relative + ': unexpected dependency ' + id);
    return imports[id];
  }, module, module.exports);
  return module.exports;
}
const errors = load('src/product/chatErrors.ts');
const cooperation = load('src/product/chatCooperation.ts', { './chatErrors': errors });
const legacy = () => ({ schema_version: 'skeleton.ai.cooperation.v1', review_rounds: 1, max_stage_output_tokens: 512, roles: {} });
const policy = (drafts, rounds = 1) => ({ ...legacy(), review_rounds: rounds, ...(drafts > 1 ? { draft_count: drafts } : {}) });
const code = expected => error => error instanceof errors.ChatClientError && error.code === expected;
function summary(drafts = 1, rounds = 1, completed) {
  const ids = ['plan', ...(drafts === 1 ? ['draft'] : Array.from({ length: drafts }, (_, i) => `draft:${i + 1}`))];
  for (let i = 1; i <= rounds; i++) ids.push(`critique:${i}`, `refine:${i}`);
  const count = completed ?? ids.length;
  return { schema_version: 'skeleton.ai.cooperation.v1', policy_digest: 'a'.repeat(64), brief_digest: 'b'.repeat(64), source_snapshot_digest: 'c'.repeat(64),
    completed_stages: count, total_stages: ids.length, complete: count === ids.length, independent_review_certified: false,
    ...(drafts > 1 ? { draft_count: drafts } : {}),
    artifacts: ids.slice(0, count).map((id, i) => ({ stage_id: id, role: id.split(':')[0], output_digest: String(i).repeat(64),
      request_digest: 'd'.repeat(64), provider_receipt: `receipt-${i}`, provider: 'local', model: 'model-1' })),
  };
}

test('one-draft policies keep the legacy serialized identity and snapshot explicit roles', () => {
  assert.equal(JSON.stringify(cooperation.reviewedResponsePolicy()), JSON.stringify(legacy()));
  assert.equal(JSON.stringify(cooperation.normalizeChatCooperation(legacy())), JSON.stringify(legacy()));
  assert.equal(JSON.stringify(cooperation.normalizeChatCooperation({ ...legacy(), draft_count: 1 })), JSON.stringify(legacy()));
  const request = { ...policy(3), roles: { draft: { provider_id: 'local', model_id: 'model-1' } } };
  const normalized = cooperation.normalizeChatCooperation(request);
  request.roles.draft.model_id = 'different-model'; request.draft_count = 2;
  assert.equal(normalized.roles.draft.model_id, 'model-1'); assert.equal(normalized.draft_count, 3);
});

test('draft policy rejects coerced, unbounded and unknown settings', () => {
  for (const draft_count of [null, false, true, 0, -1, 4, 1.5, Infinity, NaN, '2', [], {}]) {
    assert.throws(() => cooperation.normalizeChatCooperation({ ...legacy(), draft_count }), code('invalid_cooperation_policy'));
  }
  assert.throws(() => cooperation.normalizeChatCooperation({ ...policy(3), parallel_drafts: true }), code('invalid_cooperation_policy'));
});

test('all draft and review combinations reserve each stage within the shared answer budget', () => {
  for (let drafts = 1; drafts <= 3; drafts++) for (let rounds = 1; rounds <= 3; rounds++) {
    const p = policy(drafts, rounds), count = 1 + drafts + 2 * rounds, minimum = count * 64;
    assert.equal(cooperation.cooperationStageCount(p), count);
    assert.equal(cooperation.minimumCooperationTokens(p), minimum);
    assert.deepEqual(cooperation.cooperationConfigurationIssues(p, [], minimum), []);
    const issues = cooperation.cooperationConfigurationIssues(p, [], minimum - 1);
    assert.equal(issues.length, 1); assert.match(issues[0], new RegExp(`${count} model stages`));
    assert.deepEqual(cooperation.cooperationConfigurationIssues(p, [], undefined), []);
  }
});

test('every valid stage prefix remains observable for all bounded draft and round counts', () => {
  for (let drafts = 1; drafts <= 3; drafts++) for (let rounds = 1; rounds <= 3; rounds++) {
    for (let completed = 0; completed <= 1 + drafts + 2 * rounds; completed++) {
      const observation = summary(drafts, rounds, completed);
      assert.equal(cooperation.validateChatCooperationSummary(observation), observation);
    }
  }
});

test('summary rejects malformed draft counts and inconsistent stage budgets before any receipt', () => {
  for (const draft_count of [null, false, true, 0, 1, 4, 2.5, '3', Infinity]) {
    assert.throws(() => cooperation.validateChatCooperationSummary({ ...summary(3, 1, 0), draft_count }), code('invalid_cooperation_evidence'));
  }
  for (const total_stages of [0, 3, 4, 5, 7, 11, 12, '6', NaN]) {
    assert.throws(() => cooperation.validateChatCooperationSummary({ ...summary(3, 1, 0), total_stages }), code('invalid_cooperation_evidence'));
  }
});

test('recorded candidate order, receipts and completion cannot be invented or skipped', () => {
  const invalid = edit => { const value = summary(3); edit(value); assert.throws(() => cooperation.validateChatCooperationSummary(value), code('invalid_cooperation_evidence')); };
  invalid(value => { value.artifacts[1].stage_id = 'draft'; });
  invalid(value => { value.artifacts[2].stage_id = 'draft:3'; });
  invalid(value => { value.artifacts[3].role = 'refine'; });
  invalid(value => { value.artifacts[3].provider_receipt = value.artifacts[1].provider_receipt; });
  invalid(value => { value.complete = false; });
  invalid(value => { value.independent_review_certified = true; });
  invalid(value => { value.artifacts.pop(); });
});

test('reconciliation preserves progress and rejects draft-count changes even with equal total stages', () => {
  const earlier = summary(3, 1, 1), later = summary(3, 1, 4);
  assert.equal(cooperation.reconcileChatCooperation(earlier, later), later);
  assert.equal(cooperation.reconcileChatCooperation(later, earlier), later);
  // One draft + two rounds and three drafts + one round both have six stages.
  assert.throws(() => cooperation.reconcileChatCooperation(summary(1, 2, 0), summary(3, 1, 0)), code('cooperation_identity_changed'));
  const altered = summary(3, 1, 4); altered.artifacts[0].request_digest = 'e'.repeat(64);
  assert.throws(() => cooperation.reconcileChatCooperation(later, altered), code('cooperation_receipt_changed'));
});

test('all draft receipts must belong to the canonical turn', () => {
  const observed = summary(3), receipts = observed.artifacts.map(value => value.provider_receipt);
  cooperation.validateChatCooperationReceipts(observed, receipts);
  assert.throws(() => cooperation.validateChatCooperationReceipts(observed, receipts.filter(value => value !== 'receipt-2')), code('cooperation_receipts_unbound'));
  assert.throws(() => cooperation.validateChatCooperationReceipts(observed, [...receipts, receipts[0]]), code('cooperation_receipts_unbound'));
});

test('canonical chat transport serializes the chosen drafts with the original budget and request identity', async () => {
  const posts = [];
  const api = { async post(url, body, options) { posts.push({ url, body, options }); return { ok: true, data: { success: false, accepted: true, terminal: false } }; } };
  const client = load('src/product/governedConversationClient.ts', {
    'expo-crypto': {}, '../utils/apiClient': { __esModule: true, default: api }, './conversationProjection': {},
    '../auth/gameforgeAuth': { authHeaders: headers => headers ?? {} }, './chatErrors': errors, './chatCooperation': cooperation,
  });
  const thread = { thread_id: 'thread-1', version: 7 };
  await client.startConversationTurn(thread, { message: 'Original request', context: 'Original context', idempotencyKey: 'request-1',
    maxOutputTokens: 1024, cooperation: policy(3), providerId: 'local', modelId: 'model-1' });
  assert.equal(posts.length, 1); assert.equal(posts[0].url, '/api/ai/chat');
  assert.deepEqual(posts[0].body.cooperation, policy(3)); assert.equal(posts[0].body.max_output_tokens, 1024);
  assert.equal(posts[0].body.context, 'Original context'); assert.equal(posts[0].body.idempotency_key, 'request-1');
  assert.equal(posts[0].body.expected_thread_version, 7); assert.equal(posts[0].options.idempotencyKey, 'request-1');
  assert.equal(posts[0].options.retries, 0);
  await assert.rejects(client.startConversationTurn(thread, { message: 'Request', idempotencyKey: 'request-2', cooperation: { ...legacy(), draft_count: 50 } }), code('invalid_cooperation_policy'));
  assert.equal(posts.length, 1);
});

test('interrupted device work retains the exact multi-draft policy instead of adopting new settings', () => {
  const workspace = load('src/features/Jeeves/workspace.ts', { '../../product/chatCooperation': cooperation });
  const saved = workspace.createWorkspace(), conversation = saved.conversations[0];
  conversation.messages.push({ id: 'message-1', role: 'user', text: 'Saved request', createdAt: 123, status: 'pending',
    retryRequest: { session_id: 'session-1', context: 'Saved context', force_all_forms: false, max_output_tokens: 1024, cooperation: policy(3, 2) } });
  const restored = workspace.decodeWorkspace(workspace.encodeWorkspace(saved));
  const message = restored.conversations[0].messages[0];
  assert.equal(message.status, 'failed'); assert.deepEqual(message.retryRequest.cooperation, policy(3, 2));
  assert.equal(message.retryRequest.max_output_tokens, 1024);
  conversation.messages[0].retryRequest.cooperation.draft_count = 4;
  const invalid = workspace.decodeWorkspace(workspace.encodeWorkspace(saved)).conversations[0].messages[0];
  assert.equal(invalid.retryRequest.resume_only, true); assert.equal(invalid.retryRequest.cooperation, undefined);
});

function controlFixture(initial = legacy(), disabled = false) {
  const slots = []; let cursor = 0, current = initial, tree;
  const node = (type, props) => typeof type === 'function' ? type(props) : { type, props: props ?? {} };
  const React = { useState(initialValue) { const i = cursor++; if (!slots[i]) slots[i] = { value: initialValue };
    return [slots[i].value, value => { slots[i].value = typeof value === 'function' ? value(slots[i].value) : value; }]; }, useEffect() {} };
  const native = { StyleSheet: { create: value => value } };
  for (const type of ['Modal', 'SafeAreaView', 'ScrollView', 'Text', 'TextInput', 'TouchableOpacity', 'View']) native[type] = type;
  const Component = load('src/features/Jeeves/ChatResponseReviewControl.tsx', {
    react: { __esModule: true, default: React, ...React }, 'react/jsx-runtime': { jsx: node, jsxs: node, Fragment: 'Fragment' },
    'react-native': native, '../../product/chatCooperation': cooperation,
  }).default;
  function find(value, label) {
    if (!value || typeof value !== 'object') return undefined;
    if (Array.isArray(value)) { for (const child of value) { const found = find(child, label); if (found) return found; } return undefined; }
    if (value.props?.accessibilityLabel === label) return value;
    return find(value.props?.children, label);
  }
  function text(value) {
    if (typeof value === 'string' || typeof value === 'number') return String(value);
    if (Array.isArray(value)) return value.map(text).join('');
    return value && typeof value === 'object' ? text(value.props?.children) : '';
  }
  const result = {
    render() { cursor = 0; tree = Component({ enabled: true, disabled, change() {}, policy: current, changePolicy(value) { current = value; }, models: [],
      fieldError: null, changeFieldError() {}, issues: [], answerTokenLimit: 1024, async refreshModels() { throw new Error('No model refresh requested'); } }); return result; },
    choice(label) { const found = find(tree, label); assert.ok(found, 'Missing ' + label); return found.props; },
    policy: () => current, text: () => text(tree),
  };
  return result.render();
}

test('real review controls select multiple candidates and return to the legacy one-draft policy', () => {
  const control = controlFixture();
  assert.equal(control.choice('1 draft candidate').accessibilityState.checked, true);
  control.choice('3 draft candidates').onPress(); control.render();
  assert.deepEqual(control.policy(), policy(3)); assert.equal(control.choice('3 draft candidates').accessibilityState.checked, true);
  assert.match(control.text(), /6 model stages/); assert.match(control.text(), /at least 384 total tokens/);
  assert.match(control.text(), /one at a time using the drafting model/);
  control.choice('2 review rounds').onPress(); control.render();
  assert.deepEqual(control.policy(), policy(3, 2)); assert.match(control.text(), /8 model stages/);
  control.choice('1 draft candidate').onPress(); control.render();
  assert.equal(Object.hasOwn(control.policy(), 'draft_count'), false);
  assert.equal(control.policy().review_rounds, 2); assert.match(control.text(), /6 model stages/);
});

test('disabled pending-turn controls cannot offer an editable draft count', () => {
  const control = controlFixture(policy(3), true);
  for (const label of ['1 draft candidate', '2 draft candidates', '3 draft candidates']) {
    assert.equal(control.choice(label).disabled, true); assert.equal(control.choice(label).accessibilityState.disabled, true);
  }
  assert.deepEqual(control.policy(), policy(3));
});

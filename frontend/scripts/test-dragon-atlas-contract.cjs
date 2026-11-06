/* Hermetic Dragon Atlas source/client regression suite. No network effects. */
'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const root = path.join(__dirname, '..');
const clientPath = path.join(root, 'src/product/crawlerClient.ts');
const panelPath = path.join(root, 'src/features/Jeeves/CrawlerResearchAtlasPanel.tsx');
const workspacePath = path.join(root, 'src/features/Jeeves/CrawlerWorkspace.tsx');
const H = 'a'.repeat(64);
let token = 'operator-one', response = null, posts = [];
class ChatClientError extends Error {
  constructor(message, options = {}) { super(message); Object.assign(this, options); }
}
function transpile(file) {
  const source = fs.readFileSync(file, 'utf8');
  const syntax = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true,
    file.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
  assert.equal(syntax.parseDiagnostics.length, 0, 'TypeScript/JSX syntax errors');
  const result = ts.transpileModule(source, {
    fileName: file, reportDiagnostics: true,
    compilerOptions: { target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  });
  assert.deepEqual((result.diagnostics || [])
    .filter(x => x.category === ts.DiagnosticCategory.Error)
    .map(x => ts.flattenDiagnosticMessageText(x.messageText, '\n')), []);
  return result.outputText;
}
const api = {
  post: async (url, body) => {
    posts.push({ url, body });
    return { ok: true, data: response, status: 200 };
  },
};
function loadClient() {
  const module = { exports: {} };
  const dependencies = {
    'expo-crypto': { CryptoDigestAlgorithm: { SHA256: 'sha256' }, digestStringAsync: async () => H },
    '../utils/apiBase': { API_BASE: 'https://example.invalid' },
    '../utils/apiClient': { default: api },
    '../auth/gameforgeAuth': { authHeaders: () => ({}), getAuthToken: () => token },
    './chatErrors': { ChatClientError, chatApiError: () => new ChatClientError('server rejected') },
  };
  new Function('require','module','exports',transpile(clientPath))(
    name => {
      if (!(name in dependencies)) throw new Error('Unexpected client dependency: ' + name);
      return dependencies[name];
    }, module, module.exports,
  );
  return module.exports;
}
const client = loadClient();
const objective = () => ({
  objective_id: 'operator-goal', question: 'What source methodology was recorded?',
  dimension: 'method', stage: 'verification', priority: 0.9,
  minimum_reviewable_passages: 1, minimum_attested_groups: 1,
  max_source_age_seconds: 3600, required_terms: [], blocked_terms: [],
});
const request = () => ({ objectives: [objective()], retrieval_mode: 'fusion' });
function fixture() {
  return {
    schema_version: 'skeleton.dragon.campaign_atlas_dashboard.v1',
    session_id: 'session-1', run_id: 'run-1', run_sequence: 1,
    snapshot_digest: H, mandate_digest: H, atlas_digest: H,
    dashboard_digest: H, issued_at: 100,
    stages: Array.from({length: 23}, (_, ordinal) => ({
      ordinal, name: 'stage-' + ordinal, receipt_digest: H, chain_digest: H,
    })),
    source_policy: { digest: H, sources_seen: 1, included_source_count: 1,
      excluded_source_count: 0, complete_current_policy_required: true },
    objectives: [], query_lattice: { digest: H, queries: 1,
      source_authority: 'operator_objectives_only' },
    retrieval: { digest: H, mode: 'fusion', candidate_passages: 1,
      retained_hits: 1, distinct_hosts: 1, evidence: [] },
    lexical_ranking: null,
    context: { digest: H, source_references: 1, serialized_bytes: 20,
      raw_source_text_redacted: true, fresh_policy_recheck_required: true },
    numeric_signals: { report_digest: H, observed_quantities: 0,
      cross_source_review_candidates: 0, unit_families: [], candidates: [],
      facts_verified: false },
    temporal_signals: { report_digest: H, date_mentions: 0, date_groups: 0,
      groups: [], remote_freshness_verified: false },
    evidence_graph: { graph_digest: H, vertices: 1, arcs: 0, retained_passages: 0,
      sources: 1, held_sources: 0, graph_is_factual_proof: false,
      objective_neighborhoods: [] },
    review_operations: { agenda_digest: H, replay_digest: H, tasks_total: 1,
      pending_tasks: 1, blocked_tasks: 0, ready_task_ids: [],
      task_types: { passage_integrity: 1 },
      recommended_queue: [{ task_id: 'r1', type: 'passage_integrity',
        objective_id: 'operator-goal', source_id: 'source-1', priority: 0.9,
        predecessors: [], current_status: 'pending_human_review',
        automatically_approvable: false }],
      human_review_recorded: false, durable_review_mutations: false },
    review_portfolio: null,
    jeeves_handoff: { manifest_digest: H, citation_count: 1, task_count: 1,
      body_excluded: true, network_called: false, dispatch_granted: false,
      requires_fresh_source_policy: true },
    citation_manifest: { manifest_digest: H, exact_anchored_references: 1,
      body_redacted: true, publication_permission: false },
    canonical_routes: { route_digest: H, node_count: 1,
      committed_parent_arcs: 0, components: 1, unreachable_pending: 0,
      unknown_parent_urls: 0, host_load: [], network_authority: false },
    slice_simulation: { simulation_digest: H, projected_request_slots: 0,
      projected_byte_reserve: 0, remaining_requests: 10,
      remaining_bytes: 10000, steps: [], held_urls: [], blockers: [],
      physical_worker_authorized: false, network_committed: false,
      real_robots_admission_executed: false },
    dispatch_recovery: { ledger_digest: H, retained_event_count: 0,
      event_history_incomplete: false, pending_dispatch: false,
      uncertain_bytes: 0, hosts: [], recovery_queue: [],
      physical_worker_join_confirmed: false, mongo_commit_confirmed: false,
      uncertain_bytes_refunded: false },
    scorecard: { digest: H, dimensions: [], alerts: [],
      advisory_priority: 0.1, decision: 'human_review_hold' },
    read_only: true, network_executed: false,
    publication_granted: false, training_permission: false, review_required: true,
  };
}
function setup(report = fixture()) { token = 'operator-one'; response = { report }; posts = []; }

test('panel and surrounding workspace compile as TSX', () => {
  assert.match(transpile(panelPath), /CrawlerResearchAtlasPanel/);
  assert.match(transpile(workspacePath), /CrawlerResearchAtlasPanel/);
  const code = fs.readFileSync(workspacePath, 'utf8');
  assert.equal((code.match(/<CrawlerResearchAtlasPanel /g) || []).length, 1);
});

test('bounded read-only Atlas request sends exactly one authenticated POST', async () => {
  setup();
  const value = await client.getCrawlAtlas('session-1', request());
  assert.equal(posts.length, 1);
  assert.equal(posts[0].url, '/api/dragon-academy/crawler/sessions/session-1/research/atlas');
  assert.equal(posts[0].body.retrieval_mode, 'fusion');
  assert.equal(value.read_only, true);
  assert.equal(value.training_permission, false);
});

test('nonmatching retrieval algorithm is rejected', async () => {
  setup();
  await assert.rejects(client.getCrawlAtlas('session-1',
    { ...request(), retrieval_mode: 'lexical_bm25' }), /incomplete or violates/);
});

test('foreign session, staged digest mismatch and alleged external effects are rejected', async () => {
  for (const change of [
    a => { a.session_id = 'another'; },
    a => { a.stages.pop(); },
    a => { a.source_policy.included_source_count = 2; },
    a => { a.publication_granted = true; },
    a => { a.jeeves_handoff.network_called = true; },
    a => { a.context.raw_source_text_redacted = false; },
    a => { a.dispatch_recovery.mongo_commit_confirmed = true; },
    a => { a.review_operations.human_review_recorded = true; },
  ]) {
    const body = fixture(); change(body); setup(body);
    await assert.rejects(client.getCrawlAtlas('session-1', request()),
      /incomplete or violates/);
  }
});

test('unbounded objectives cannot cross the transport boundary', async () => {
  setup();
  for (const mutation of [
    { question: '' }, { question: 'a'.repeat(513) }, { priority: 1.5 },
    { required_terms: ['x'] }, { required_terms: ['valid', 'valid'] },
    { required_terms: ['valid'], blocked_terms: ['valid'] },
  ]) {
    await assert.rejects(client.getCrawlAtlas('session-1', {
      ...request(), objectives: [{ ...objective(), ...mutation }],
    }), /Research goals need valid/);
  }
  assert.equal(posts.length, 0);
});

test('review estimates are bounded and never falsely described as measured', async () => {
  setup();
  for (const effort of [
    [{ task_type: 'passage_integrity', estimated_minutes: 0, estimate_basis: 'operator_estimate' }],
    [{ task_type: 'passage_integrity', estimated_minutes: 12, estimate_basis: 'measured_history' }],
    [{ task_type: 'passage_integrity', estimated_minutes: 12, estimate_basis: 'operator_estimate' },
     { task_type: 'passage_integrity', estimated_minutes: 12, estimate_basis: 'operator_estimate' }],
  ]) {
    await assert.rejects(client.getCrawlAtlas('session-1',
      { ...request(), review_effort: effort }), /explicit finite review-effort/);
  }
  await assert.rejects(client.getCrawlAtlas('session-1',
    { ...request(), review_budget_minutes: 1441 }), /finite human-review/);
  assert.equal(posts.length, 0);
});

test('operator-approved estimates may produce nonpersisted review-only plan', async () => {
  const f = fixture();
  f.review_portfolio = { portfolio_digest: H, estimated_minutes: 12,
    budget_minutes: 60, selected_count: 1, task_ids: ['r1'],
    persistence_performed: false, effort_is_observed: false };
  setup(f);
  const data = await client.getCrawlAtlas('session-1', {
    ...request(), review_budget_minutes: 60,
    review_effort: [{ task_type: 'passage_integrity',
      estimated_minutes: 12, estimate_basis: 'operator_estimate' }],
  });
  assert.equal(data.review_portfolio.persistence_performed, false);
  assert.equal(data.review_operations.durable_review_mutations, false);
});

test('account switch while awaiting transport rejects stale source data', async () => {
  setup();
  const pending = client.getCrawlAtlas('session-1', request());
  token = 'operator-two';
  await assert.rejects(pending, /Your account changed/);
  token = 'operator-one';
});

const planPath = path.join(root, 'src/features/Jeeves/atlasCampaignPlan.ts');
function loadCampaignPlan() {
  const module = { exports: {} };
  new Function('require', 'module', 'exports', transpile(planPath))(
    name => { throw new Error('Campaign plan must not import runtime authority: ' + name); },
    module, module.exports,
  );
  return module.exports;
}
const campaign = loadCampaignPlan();
const draft = (question = 'Which archive methodology is supported?') => ({
  ...campaign.NEW_ATLAS_DRAFT, question,
});

test('bounded multi-objective campaign preserves every explicit operator question', () => {
  let goals = [];
  goals = campaign.enqueueAtlasObjective(goals, draft('Which archive methodology is supported?'));
  goals = campaign.enqueueAtlasObjective(goals, {
    ...draft('Which alternative observations challenge the method?'),
    stage: 'review', dimension: 'counterexample', priority: '0.75',
    requiredTerms: 'method, comparison', blockedTerms: 'advertisement spam',
    passageTarget: '3', independenceTarget: '2', maxAgeMinutes: '120',
  });
  assert.equal(goals.length, 2);
  assert.equal(goals[0].objective_id, 'operator-goal-01');
  assert.equal(goals[1].objective_id, 'operator-goal-02');
  assert.equal(goals[1].priority, 0.75);
  assert.equal(goals[1].minimum_reviewable_passages, 3);
  assert.equal(goals[1].minimum_attested_groups, 2);
  assert.equal(goals[1].max_source_age_seconds, 7200);
  assert.deepEqual(goals[1].required_terms, ['method', 'comparison']);
  assert.deepEqual(goals[1].blocked_terms, ['advertisement', 'spam']);
  assert.deepEqual(campaign.compileAtlasCampaign(goals, {
    ...campaign.NEW_ATLAS_DRAFT, question: '',
  }), goals);
});

test('eight-objective cap never discards older research goals', () => {
  let goals = [];
  for (let i = 1; i <= campaign.MAX_ATLAS_OBJECTIVES; i++) {
    goals = campaign.enqueueAtlasObjective(goals, draft('Which method is recorded for case ' + i + '?'));
  }
  assert.equal(goals.length, 8);
  const prior = JSON.stringify(goals);
  assert.throws(() => campaign.enqueueAtlasObjective(
    goals, draft('Which future model changed?'),
  ), /more than eight/);
  assert.throws(() => campaign.compileAtlasCampaign(
    goals, draft('Which pending query changed?'),
  ), /more than eight/);
  assert.equal(JSON.stringify(goals), prior);
});

test('removal returns immutable copy and next goal receives bounded identity', () => {
  const first = campaign.enqueueAtlasObjective([], draft('Which archive is captured?'));
  const second = campaign.enqueueAtlasObjective(first, draft('Which source was revised?'));
  const removed = campaign.removeAtlasObjective(second, first[0].objective_id);
  assert.equal(removed.length, 1);
  assert.equal(second.length, 2);
  const replacement = campaign.enqueueAtlasObjective(removed, draft('Which source policy applies?'));
  assert.equal(replacement.length, 2);
  assert.equal(replacement[1].objective_id, first[0].objective_id);
  assert.throws(() => campaign.removeAtlasObjective(replacement, 'not-a-goal'), /No matching/);
});

test('duplicate and Unicode-equivalent operator objectives are rejected', () => {
  const first = campaign.enqueueAtlasObjective([], draft('What source is current?'));
  assert.throws(() => campaign.enqueueAtlasObjective(first,
    draft('What source is current?')), /already queued/);
  assert.throws(() => campaign.enqueueAtlasObjective(first,
    draft('what SOURCE is current?')), /already queued/);
  const unicode = campaign.enqueueAtlasObjective([], draft('What is the fullwidth Ａ source?'));
  assert.throws(() => campaign.enqueueAtlasObjective(unicode,
    draft('What is the fullwidth A source?')), /already queued/);
});

test('term tokens are bounded, disjoint and source-neutral', () => {
  for (const patch of [
    { requiredTerms: 'Acapital' },
    { blockedTerms: 'a' },
    { requiredTerms: 'same same' },
    { requiredTerms: 'keep', blockedTerms: 'keep' },
    { requiredTerms: 'x'.repeat(49) },
    { requiredTerms: 'a '.repeat(17).trim() },
  ]) {
    assert.throws(() => campaign.compileAtlasObjective(
      { ...draft(), ...patch }, []), /terms|overlap/i);
  }
});

test('priority, age and research targets are strictly finite', () => {
  for (const patch of [
    { priority: '-0.2' }, { priority: '1.1' }, { priority: 'NaN' },
    { priority: '' }, { priority: '0.1234' },
    { passageTarget: '0' }, { passageTarget: '33' },
    { independenceTarget: '0' }, { independenceTarget: '17' },
    { maxAgeMinutes: '0' }, { maxAgeMinutes: '1441' },
    { maxAgeMinutes: '1.5' },
  ]) {
    assert.throws(() => campaign.compileAtlasObjective(
      { ...draft(), ...patch }, []), /bound|Priority|number|age/i);
  }
});

test('a pending unqueued question is included, not discarded', () => {
  const queued = campaign.enqueueAtlasObjective([], draft('Which source claims were captured?'));
  const compiled = campaign.compileAtlasCampaign(queued,
    draft('Which source revisions are inconsistent?'));
  assert.equal(compiled.length, 2);
  assert.equal(compiled[0].question, queued[0].question);
  assert.equal(compiled[1].question, 'Which source revisions are inconsistent?');
  assert.equal(queued.length, 1);
});

test('no implicit empty question, duplicate or outside-mandate campaign', () => {
  assert.throws(() => campaign.compileAtlasCampaign([], draft('')), /Enter a research question/);
  assert.throws(() => campaign.compileAtlasObjective(draft(''), []), /3–512/);
  assert.throws(() => campaign.compileAtlasObjective({
    ...draft(), stage: 'model_execution',
  }, []), /Unsupported objective/);
  assert.throws(() => campaign.compileAtlasObjective({
    ...draft(), dimension: 'publisher',
  }, []), /Unsupported objective/);
});

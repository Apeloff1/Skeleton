/* Hermetic Dragon Atlas source/client regression suite. No network effects. */
'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const NodeModule = require('node:module');
const ts = require('typescript');
const root = path.join(__dirname, '..');
const clientPath = path.join(root, 'src/product/crawlerClient.ts');
const panelPath = path.join(root, 'src/features/Jeeves/CrawlerResearchAtlasPanel.tsx');
const workspacePath = path.join(root, 'src/features/Jeeves/CrawlerWorkspace.tsx');
const H = 'a'.repeat(64);
const OPERATION_STAGES = [
  'exact_canonical_event_timeline',
  'per_origin_robots_and_cooldown_safety',
  'physical_worker_restart_and_cas_witness',
  'measured_resource_capacity_envelope',
  'opaque_bounded_dispatch_preflight',
  'review_only_operator_recovery_runbook',
];
const FORENSIC_STAGES = [
  'exact_selected_source_custody',
  'source_text_security_inspection',
  'anchored_passage_geometry',
  'possible_source_reuse',
  'objective_failure_counterfactual',
  'source_boilerplate_screening',
  'bounded_capture_age_analysis',
  'cross_source_sentence_echoes',
  'active_content_render_risk',
  'privacy_and_secret_exposure',
  'objective_host_concentration',
  'possible_polarity_collisions',
  'canonical_capture_provenance_posture',
  'operator_objective_grounding',
  'selected_reference_concentration',
  'mandate_consent_horizon',
  'reverse_source_objective_usage',
  'policy_bound_research_deficit_matrix',
  'untrusted_context_resource_budget',
  'captured_extraction_quality_diagnostics',
  'operator_query_rank_support_audit',
  'captured_origin_redirect_hygiene',
  'objective_selection_fairness_metrics',
  'conservative_risky_source_ablation',
  'script_coverage_lexical_limitations',
  'review_only_forensic_queue',
];
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
function loadRepositorySource(file, dependencies) {
  // The only executable sources are explicitly approved, repository-owned TS
  // files. Never compile a URL, operator input, or an arbitrary runtime path.
  if (file !== clientPath && file !== path.join(root, 'src/features/Jeeves/atlasCampaignPlan.ts')) {
    throw new Error('Unexpected Dragon test source');
  }
  const loaded = new NodeModule(file, module);
  loaded.filename = file;
  loaded.paths = [];
  loaded.require = name => {
    if (!Object.prototype.hasOwnProperty.call(dependencies, name)) {
      throw new Error('Unexpected Dragon test dependency: ' + name);
    }
    return dependencies[name];
  };
  loaded._compile(transpile(file), file);
  return loaded.exports;
}
const api = {
  post: async (url, body) => {
    posts.push({ url, body });
    return { ok: true, data: response, status: 200 };
  },
};
function loadClient() {
  const dependencies = {
    'expo-crypto': { CryptoDigestAlgorithm: { SHA256: 'sha256' }, digestStringAsync: async () => H },
    '../utils/apiBase': { API_BASE: 'https://example.invalid' },
    '../utils/apiClient': { default: api },
    '../auth/gameforgeAuth': { authHeaders: () => ({}), getAuthToken: () => token },
    './chatErrors': { ChatClientError, chatApiError: () => new ChatClientError('server rejected') },
  };
  return loadRepositorySource(clientPath, dependencies);
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
    stages: Array.from({length: 26}, (_, ordinal) => ({
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
    forensics: {
      report_digest: H, frame_set_digest: H, atlas_digest: H,
      source_policy_digest: H, retrieval_digest: H,
      stages: FORENSIC_STAGES.map((name, ordinal) => ({
        ordinal, name,
        receipt_digest: H, chain_digest: H,
      })),
      selected_passages: 1, selected_sources: 1,
      security_held_passages: 0, security_held_sources: 0,
      active_content_held_sources: 0, privacy_held_sources: 0,
      cross_host_sentence_echoes: 0, source_reuse_components: 0,
      possible_polarity_collisions: 0, low_information_passages: 0,
      capture_age_held_sources: 0, overlap_excess_characters: 0,
      concentrated_objectives: [], review_tasks: 0,
      provenance_held_sources: 0, grounding_deficit_objectives: 0,
      reference_reused_sources: 0, consent_renewal_review_due: false,
      urgent_research_gaps: 0, context_selected_utf8_bytes: 4096,
      context_budget_exceeded: false,
      extraction_held_sources: 0, query_unsupported_objectives: 0,
      origin_review_sources: 0, selection_source_dominance_objectives: 0,
      risk_ablated_objectives: 0, script_coverage_review_objectives: 0,
      critical_review_tasks: 0, review_queue: [],
      source_bodies_redacted: true, human_review_required: true,
      publication_granted: false, training_permission: false,
      network_or_model_invoked: false,
    },
    operations: {
      report_digest: H, source_snapshot_digest: H, run_sequence: 1,
      stages: OPERATION_STAGES.map((name, ordinal) => ({
        ordinal, name, receipt_digest: H, chain_digest: H,
      })),
      retained_event_count: 0, historical_events_incomplete: false,
      event_clock_integrity_review: false, pending_dispatch: false,
      uncertain_bytes: 0, inspected_origins: 2,
      unresolved_robots_origins: 2, stale_robots_origins: 0,
      observed_resource_samples: 0, hypothetical_work_candidates: 0,
      capacity_holds: ['no_measured_resource_telemetry'],
      critical_operator_steps: 1,
      operator_runbook: [{
        code: 'complete_durable_restart_fence', priority: 'critical',
        requires_backend_authority: true, automatically_executed: false,
      }],
      physical_worker_fenced: false, mongo_checkpoint_confirmed: false,
      live_robots_permission_granted: false, network_executed: false,
      source_text_redacted: true, read_only: true,
      automatic_recovery_authorized: false,
    },
    evidence_family_stress: {
      stress_digest: H, policy_digest: H, retrieval_digest: H,
      robustness_digest: H, similarity_digest: H,
      selected_source_records: 1, exact_content_families: 1,
      possible_near_duplicate_clusters: 1,
      flagged_objectives: [], objectives_with_similarity_holds: [],
      objectives: [], limitations: [
        'selected_evidence_only', 'lexical_near_duplicate_is_not_proven_shared_origin',
        'near_duplicate_components_are_heuristic_collapse_scenarios',
        'unscored_sources_are_explicit_uncertainty_not_independence',
        'human_source_lineage_and_fact_review_are_mandatory',
      ],
      claim_correctness_verified: false, source_text_exported: false,
      model_or_network_invoked: false, human_review_required: true,
    },
    source_similarity: {
      audit_digest: H, retrieval_digest: H, policy_digest: H,
      selected_sources: 1, compared_sources: 1, held_sources: 0,
      eligible_pairs: 0, candidate_pairs: 0, cross_host_candidates: 0,
      skipped_oversize: 0, skipped_short: 0,
      jaccard_threshold: .78, containment_threshold: .92,
      candidate_leads: [], clusters: [],
      source_bodies_redacted: true, network_used: false,
      training_or_publication_granted: false, lineage_verified: false,
    },
    retrieval_robustness: {
      audit_digest: H, retrieval_digest: H, selected_passages: 1,
      selected_sources: 1, selected_hosts: 1,
      distinct_content_families: 1, cross_host_exact_copy_groups: 0,
      exact_copy_families: [],
      flagged_objectives: [],
      objectives: [], host_ablation: [{
        removed_host: 'example.com', removed_selected_passages: 1,
        surviving_selected_passages: 0, surviving_unique_sources: 0,
        objectives_without_evidence: [], objectives_left_with_one_host: [],
        reranking_executed: false,
      }],
      objective_reuse: [],
      limitations: ['observed_selected_passages_only',
        'unselected_candidates_and_missing_sources_not_recovered',
        'host_removal_does_not_rerank_or_fetch',
        'different_hosts_do_not_prove_independent_ownership',
        'human_source_and_claim_review_required'],
      source_bodies_excluded: true,
      verified_independence: false,
      network_or_reranking_executed: false,
    },
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

test('operator sitemap discovery is explicit, bounded and carried into the create request', () => {
  const source = fs.readFileSync(workspacePath, 'utf8');
  assert.match(source, /discover_sitemaps:\s*discoverSitemaps/);
  assert.match(source, /setDiscoverSitemaps\(false\)/);
  assert.match(source, /value=\{discoverSitemaps\}/);
  assert.match(source, /Seed XML\/gzip sitemaps, RSS\/Atom or JSON Feed/);
});

test('gain-of-function crawler formats and balanced dispatch are wired through the operator workspace', () => {
  const view = fs.readFileSync(workspacePath, 'utf8');
  const client = fs.readFileSync(clientPath, 'utf8');
  assert.match(view, /frontier_strategy:\s*balancedFrontier\s*\?\s*'balanced'\s*:\s*'fifo'/);
  assert.match(view, /value=\{balancedFrontier\}/);
  assert.match(view, /setBalancedFrontier\(false\)/);
  assert.match(view, /capture Markdown, CSV, JSON\/NDJSON and inert code or configuration documents/);
  assert.match(view, /HTML\/HTTP pagination links/);
  assert.match(client, /frontier_strategy\?:\s*'fifo'\s*\|\s*'balanced'/);
  assert.match(client, /canonical bounded frontier scheduling strategy/);
});

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
    a => { a.forensics.source_bodies_redacted = false; },
    a => { a.forensics.stages.pop(); },
    a => { a.forensics.stages[14].name = 'forged_stage'; },
    a => { a.forensics.consent_renewal_review_due = 'yes'; },
    a => { a.forensics.context_selected_utf8_bytes = 999999; },
    a => { a.forensics.stages[24].name = 'forged_source_security_stage'; },
    a => { a.forensics.extraction_held_sources = -1; },
    a => { a.forensics.risk_ablated_objectives = 1.5; },
    a => { a.operations.stages[1].name = 'untrusted_authorization_override'; },
    a => { a.operations.stages.pop(); },
    a => { a.operations.source_snapshot_digest = 'b'.repeat(64); },
    a => { a.operations.hypothetical_work_candidates = 500; },
    a => { a.operations.physical_worker_fenced = true; },
    a => { a.operations.mongo_checkpoint_confirmed = true; },
    a => { a.operations.live_robots_permission_granted = true; },
    a => { a.operations.network_executed = true; },
    a => { a.operations.source_text_redacted = false; },
    a => { a.operations.operator_runbook[0].automatically_executed = true; },
    a => { a.operations.capacity_holds = ['ATTACKER_CONTEXT']; },
    a => { a.forensics.atlas_digest = 'b'.repeat(64); },
    a => { a.forensics.publication_granted = true; },
    a => { a.forensics.critical_review_tasks = 257; },
    a => { a.forensics.review_queue = [{ task_id: 'bad', risk: 'critical', reason: 'injection', source_ids: [], objective_ids: [], model_may_decide: false }]; },
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
  return loadRepositorySource(planPath, {});
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


test('retrieval sensitivity metadata must bind exact selected passages', async () => {
  setup();
  const r = await client.getCrawlAtlas('session-1', request());
  assert.equal(r.retrieval_robustness.retrieval_digest, r.retrieval.digest);
  assert.equal(r.retrieval_robustness.verified_independence, false);
  assert.equal(r.retrieval_robustness.network_or_reranking_executed, false);
});

test('forged host-ablation trust or malformed concentration fails closed', async () => {
  for (const change of [
    x => { x.retrieval_robustness.retrieval_digest = 'f'.repeat(64); },
    x => { x.retrieval_robustness.verified_independence = true; },
    x => { x.retrieval_robustness.network_or_reranking_executed = true; },
    x => { x.retrieval_robustness.source_bodies_excluded = false; },
    x => { x.retrieval_robustness.host_ablation[0].reranking_executed = true; },
    x => { x.retrieval_robustness.objectives = [{
      objective_id: 'operator-goal', dominant_host_fraction: 7,
      independence_confirmed: false,
    }]; },
    x => { x.retrieval_robustness.objective_reuse = [{
      left_objective_id: 'a', right_objective_id: 'b',
      source_jaccard: 0.5, independence_proven: true,
    }]; },
  ]) {
    const r = fixture(); change(r); setup(r);
    await assert.rejects(
      client.getCrawlAtlas('session-1', request()),
      /incomplete or violates/,
    );
  }
});


test('copy-family receipts require exact content hashes and no independence grants', async () => {
  for (const change of [
    x => { x.retrieval_robustness.distinct_content_families = 100; },
    x => { x.retrieval_robustness.exact_copy_families = [{
      content_sha256: H, source_count: 2, host_count: 2,
      hosts: ['example.com', 'example.org'],
      selected_passages: 2, independence_verified: true,
    }]; },
    x => { x.retrieval_robustness.exact_copy_families = [{
      content_sha256: 'not-a-hash', source_count: 2, host_count: 2,
      hosts: ['example.com', 'example.org'],
      selected_passages: 2, independence_verified: false,
    }]; },
  ]) {
    const a = fixture(); change(a); setup(a);
    await assert.rejects(
      client.getCrawlAtlas('session-1', request()),
      /incomplete or violates/,
    );
  }
});

test('source similarity is policy bound and excludes external side effects', async () => {
  setup();
  const result = await client.getCrawlAtlas('session-1', request());
  assert.equal(result.source_similarity.policy_digest, result.source_policy.digest);
  assert.equal(result.source_similarity.retrieval_digest, result.retrieval.digest);
  assert.equal(result.source_similarity.network_used, false);
  assert.equal(result.source_similarity.lineage_verified, false);
});

test('near-duplicate forged origins and unbounded pair scores fail closed', async () => {
  for (const change of [
    a => { a.source_similarity.network_used = true; },
    a => { a.source_similarity.lineage_verified = true; },
    a => { a.source_similarity.held_sources = 2; },
    a => { a.source_similarity.policy_digest = 'f'.repeat(64); },
    a => { a.source_similarity.candidate_pairs = 497; },
    a => { a.source_similarity.candidate_pairs = 1;
           a.source_similarity.eligible_pairs = 1;
           a.source_similarity.candidate_leads = [{
             left_host: 'example.com', right_host: 'example.org',
             jaccard: 1.25, smaller_set_containment: .92,
             length_ratio: .99, relation: 'near_duplicate_review',
             cross_host: true, human_lineage_review_required: true,
             shared_origin_established: false,
           }]; },
    a => { a.source_similarity.clusters = [{
      observed_hosts: ['example.com'], source_count: 2,
      direct_candidate_edges: 1, all_pairs_verified: true,
      independent_origin_verified: false,
    }]; },
  ]) {
    const a = fixture(); change(a); setup(a);
    await assert.rejects(client.getCrawlAtlas('session-1', request()),
      /incomplete or violates/);
  }
});

test('family collapse stress keeps all apparent support unverified', async () => {
  setup();
  const r = await client.getCrawlAtlas('session-1', request());
  assert.equal(r.evidence_family_stress.robustness_digest, r.retrieval_robustness.audit_digest);
  assert.equal(r.evidence_family_stress.similarity_digest, r.source_similarity.audit_digest);
  assert.equal(r.evidence_family_stress.claim_correctness_verified, false);
  assert.equal(r.evidence_family_stress.human_review_required, true);
});

test('forged factual independence and impossible source-family counts fail closed', async () => {
  for (const change of [
    x => { x.evidence_family_stress.claim_correctness_verified = true; },
    x => { x.evidence_family_stress.human_review_required = false; },
    x => { x.evidence_family_stress.model_or_network_invoked = true; },
    x => { x.evidence_family_stress.source_text_exported = true; },
    x => { x.evidence_family_stress.exact_content_families = 5; },
    x => { x.evidence_family_stress.possible_near_duplicate_clusters = 2; },
    x => { x.evidence_family_stress.similarity_digest = 'f'.repeat(64); },
    x => { x.evidence_family_stress.objectives = [{
      objective_id: 'operator-goal',
      target_attested_groups: 2, selected_source_records: 1,
      exact_content_families: 1, possible_near_duplicate_clusters: 1,
      unscored_sources: 0, hypothetical_target_shortfall: 1,
      independent_evidence_attested: true,
    }]; },
  ]) {
    const x = fixture(); change(x); setup(x);
    await assert.rejects(client.getCrawlAtlas('session-1', request()),
      /incomplete or violates/);
  }
});

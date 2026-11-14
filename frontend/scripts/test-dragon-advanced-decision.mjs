/**
 * Dragon Advanced Decision Cockpit: hostile, deterministic source-only tests.
 * Executed after construction via Node 24's built-in TypeScript stripping.
 * No network, no mocked "live" model, no database, and no release authority.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import {
  buildAdvancedDecisionBoard, formatAdvancedDecisionBrief,
} from '../src/features/Jeeves/dragonResearchDecisionEngine.ts';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const H = letter => letter.repeat(64);
const IDS = ['operator-goal-01', 'operator-goal-02', 'operator-goal-03'];
const session = () => ({
  session_id: 'owned-mission', version: 7, consent_current: true,
  title: 'private mission', status: 'completed',
});
const goal = (id, min = 2) => ({
  objective_id: id, question: 'Confirm observed effect',
  dimension: 'method', stage: 'verification', priority: 0.9,
  minimum_reviewable_passages: min, minimum_attested_groups: 2,
  max_source_age_seconds: 3600, required_terms: [], blocked_terms: [],
});
function fixture() {
  const report = {
    session_id: 'owned-mission', run_sequence: 3, atlas_digest: H('a'),
    snapshot_digest: H('b'), dashboard_digest: H('c'),
    read_only: true, network_executed: false, publication_granted: false,
    training_permission: false, review_required: true,
    pilot_qualification: {
      schema_version: 'skeleton.dragon.campaign_pilot_qualification.v1',
      atlas_digest: H('a'), snapshot_digest: H('b'),
      source_policy_digest: H('d'), run_sequence: 3,
      qualification_digest: H('e'), source_only: true, read_only: true,
      training_authorized: false, publication_authorized: false,
      release_authorized: false, recheck_mongo_authority_before_any_followup: true,
    },
    source_policy: { digest: H('d'), sources_seen: 4,
      included_source_count: 4, excluded_source_count: 0 },
    objectives: IDS.map((objective_id, i) => ({
      objective_id, dimension: 'method', stage: 'verification', priority: 1 - i * .2,
    })),
    retrieval_robustness: {
      selected_hosts: 3, selected_passages: 6, distinct_content_families: 3,
      flagged_objectives: [IDS[0]],
      objectives: [
        { objective_id: IDS[0], selected_passages: 0,
          distinct_selected_sources: 0, distinct_selected_hosts: 0,
          distinct_content_families: 0, cross_host_exact_content_reuse: false,
          risk: 'no_selected_evidence' },
        { objective_id: IDS[1], selected_passages: 4,
          distinct_selected_sources: 2, distinct_selected_hosts: 1,
          distinct_content_families: 1, cross_host_exact_content_reuse: true,
          risk: 'single_host' },
        { objective_id: IDS[2], selected_passages: 2,
          distinct_selected_sources: 2, distinct_selected_hosts: 2,
          distinct_content_families: 2, cross_host_exact_content_reuse: false,
          risk: 'multiple_observed_hosts' },
      ],
      host_ablation: [
        { removed_host: 'source-a.example.org',
          objectives_without_evidence: [IDS[1]],
          objectives_left_with_one_host: [IDS[2]] },
        { removed_host: 'source-b.example.org',
          objectives_without_evidence: [], objectives_left_with_one_host: [] },
      ],
    },
    evidence_family_stress: {
      objectives: IDS.map((objective_id, i) => ({
        objective_id, target_attested_groups: 2,
        possible_near_duplicate_clusters: i === 1 ? 1 : 0,
        hypothetical_target_shortfall: i === 1 ? 1 : 0,
      })),
    },
    evidence_graph: { objective_neighborhoods: IDS.map(objective_id => ({
      objective_id, source_count: 2,
    })) },
    forensics: {
      review_queue: [
        { task_id: 'rev-a', risk: 'critical', objective_ids: [IDS[0]] },
        { task_id: 'rev-b', risk: 'high', objective_ids: [IDS[1]] },
      ],
      query_unsupported_objectives: 0,
      security_held_sources: 0, privacy_held_sources: 0,
    },
    review_operations: {
      tasks_total: 5, pending_tasks: 4, blocked_tasks: 1,
      ready_task_ids: ['rev-a', 'rev-b', 'rev-c', 'rev-dependent'],
      recommended_queue: [
        { task_id: 'rev-a', type: 'objective_gap', objective_id: IDS[0],
          priority: 0.9, predecessors: [], current_status: 'pending_human_review' },
        { task_id: 'rev-b', type: 'claim_corroboration', objective_id: IDS[1],
          priority: 0.7, predecessors: [], current_status: 'pending_human_review' },
        { task_id: 'rev-c', type: 'source_provenance', objective_id: IDS[2],
          priority: 0.4, predecessors: [], current_status: 'pending_human_review' },
        { task_id: 'rev-dependent', type: 'human_fact_review', objective_id: IDS[0],
          priority: 0.95, predecessors: ['rev-a'],
          current_status: 'pending_human_review' },
      ],
    },
    source_similarity: { candidate_pairs: 2 },
    operations: { unresolved_robots_origins: 1, pending_dispatch: false,
      uncertain_bytes: 0 },
  };
  return report;
}
function make(report = fixture(), owner = session(), goals = IDS.map(id => goal(id)),
  host = null, budget = 90, cost = 12) {
  return buildAdvancedDecisionBoard(report, owner, goals, host, budget, cost);
}

test('three-layer triage is deterministic, sorted and never claims factual authority', () => {
  const first = make(), second = make();
  assert.deepEqual(first, second);
  assert.equal(first.objectiveCount, 3);
  assert.deepEqual(first.objectiveDecisions.map(x => x.severity),
    ['critical', 'high', 'review']);
  assert.equal(first.criticalObjectives, 1);
  assert.equal(first.highObjectives, 1);
  assert.equal(first.externalReleaseAuthorized, false);
  assert.equal(first.factualVerificationEstablished, false);
  assert.equal(first.independentSourceAttestationEstablished, false);
  assert.equal(first.networkCalled, false);
  assert.equal(first.persisted, false);
  assert.equal(first.humanReviewRequired, true);
  assert.equal(first.objectiveDecisions[0].independentGroupsVerified, 0);
  assert.equal(first.objectiveDecisions[1].nearDuplicateClusters, 1);
  assert.equal(first.sourcePolicyExcluded, 0);
  assert.ok(Object.isFrozen(first));
});

test('passage targets use exact operator goals, no imaginary independent witness', () => {
  const result = make();
  assert.equal(result.objectiveDecisions[0].targetPassages, 2);
  assert.equal(result.objectiveDecisions[0].apparentPassageDeficit, 2);
  assert.equal(result.objectiveDecisions[1].apparentPassageDeficit, 0);
  assert.ok(result.objectiveDecisions.every(row =>
    row.independentGroupsVerified === 0 && row.targetAttestedGroups === 2));
  const withoutGoal = make(fixture(), session(), []);
  assert.equal(withoutGoal.objectiveDecisions[0].targetPassages, null);
  assert.equal(withoutGoal.objectiveDecisions[0].apparentPassageDeficit, null);
});

test('host-loss scenarios only project canonical ablation receipts', () => {
  const report = fixture();
  const old = JSON.stringify(report);
  const base = make(report);
  const impact = make(report, session(), IDS.map(id => goal(id)),
    'source-a.example.org');
  assert.equal(impact.objectiveDecisions[0].lostAllEvidenceUnderScenario, false);
  assert.equal(impact.objectiveDecisions[1].lostAllEvidenceUnderScenario, true);
  assert.equal(impact.objectiveDecisions[2].scenarioHostCountDropsToOne, true);
  assert.equal(impact.criticalObjectives, 2);
  assert.ok(impact.objectiveDecisions[1].reasons.includes('host_loss'));
  assert.equal(base.objectiveDecisions[1].lostAllEvidenceUnderScenario, false);
  assert.equal(JSON.stringify(report), old, 'projection must never edit Atlas');
  assert.throws(() => make(report, session(), [], 'foreign.example.org'),
    /unknown host-loss scenario/);
  assert.throws(() => make(report, session(), [], ''),
    /unknown host-loss scenario/);
});

test('review planner budgets only genuinely ready, predecessor-free tasks', () => {
  const result = make(fixture(), session(), [], null, 25, 12);
  assert.equal(result.budgetedTasks, 2);
  assert.equal(result.budgetUsedMinutes, 24);
  assert.equal(result.heldTasks, 1);
  assert.equal(result.unlistedTasks, 1);
  const ids = result.reviewDecisions.filter(x => x.status === 'budgeted_now')
    .map(x => x.taskId);
  assert.deepEqual(ids, ['rev-a', 'rev-b']);
  assert.equal(result.reviewDecisions.find(x =>
    x.taskId === 'rev-dependent').status, 'dependency_held');
  assert.ok(result.reviewDecisions.every(x => x.humanApprovalRequired
    && x.actionExecuted === false));
});
test('denied ready identifiers and unresolved prerequisites never self-complete', () => {
  const report = fixture();
  report.review_operations.ready_task_ids = ['rev-a', 'rev-dependent'];
  const plan = make(report);
  assert.equal(plan.budgetedTasks, 1);
  assert.equal(plan.heldTasks, 3);
  assert.equal(plan.reviewDecisions.find(x =>
    x.taskId === 'rev-dependent').status, 'dependency_held');
});
test('review minutes and source counters stay within bounded safety envelope', () => {
  for (const budget of [0, 10, 481, NaN, Infinity, 90.5]) {
    assert.throws(() => make(fixture(), session(), [], null, budget),
      /budget/);
  }
  for (const cost of [0, 4, 121, NaN, -1, 12.2]) {
    assert.throws(() => make(fixture(), session(), [], null, 90, cost),
      /budget/);
  }
  const bad = fixture();
  bad.source_policy.excluded_source_count = 1;
  assert.throws(() => make(bad), /source-policy accounting/);
});
test('rights, role-owned session and immutable source-only receipt are required', () => {
  const changes = [
    x => { x.session_id = 'foreign'; },
    x => { x.pilot_qualification.source_only = false; },
    x => { x.pilot_qualification.read_only = false; },
    x => { x.pilot_qualification.training_authorized = true; },
    x => { x.pilot_qualification.release_authorized = true; },
    x => { x.pilot_qualification.publication_authorized = true; },
    x => { x.pilot_qualification.qualification_digest = 'bad'; },
    x => { x.pilot_qualification.snapshot_digest = H('f'); },
    x => { x.pilot_qualification.run_sequence += 1; },
    x => { x.pilot_qualification.source_policy_digest = H('f'); },
    x => { x.network_executed = true; },
    x => { x.read_only = false; },
    x => { x.review_required = false; },
  ];
  for (const change of changes) {
    const data = fixture(); change(data);
    assert.throws(() => make(data), /Unqualified Dragon decision/);
  }
  for (const revoked of [
    { ...session(), consent_current: false },
    { ...session(), session_id: 'other-owner' },
    { ...session(), version: 0 },
  ]) assert.throws(() => make(fixture(), revoked), /session ownership or consent/);
});
test('missing evidence, duplicate goals, malformed review task identities fail closed', () => {
  const cases = [
    x => { x.retrieval_robustness.objectives = []; },
    x => { x.evidence_family_stress.objectives = []; },
    x => { x.evidence_graph.objective_neighborhoods = []; },
    x => { x.objectives[0].objective_id = '<inject>'; },
    x => { x.objectives[1].objective_id = x.objectives[0].objective_id; },
    x => { x.review_operations.recommended_queue[1].task_id = 'rev-a'; },
    x => { x.review_operations.recommended_queue[0].task_id = '<unsafe>'; },
    x => { x.review_operations.recommended_queue[0].priority = Infinity; },
    x => { x.review_operations.recommended_queue[0].predecessors = null; },
  ];
  for (const mutate of cases) {
    const x = fixture(); mutate(x);
    assert.throws(() => make(x), /Unqualified Dragon decision/);
  }
  const duplicated = IDS.map(id => goal(id)); duplicated[1].objective_id = IDS[0];
  assert.throws(() => make(fixture(), session(), duplicated), /duplicate campaign objective/);
  assert.throws(() => make(fixture(), session(), Array(9).fill(goal(IDS[0]))),
    /objective count/);
});
test('portable advanced brief is tightly bounded, discloses no URLs or source body', () => {
  const source = fixture();
  source.untrusted_text = 'secret-passphrase-do-not-export';
  source.retrieval = { evidence: [{
    canonical_url: 'https://private.example.org/secret-document',
    raw_body: 'secret-passphrase-do-not-export',
  }] };
  const board = make(source, session(), [], 'source-a.example.org', 25, 12);
  const brief = formatAdvancedDecisionBrief(board);
  assert.ok(brief.length < 7000);
  assert.match(brief, /NOT VERIFIED/);
  assert.match(brief, /NOT AUTHORIZED/);
  assert.match(brief, /human_minutes=12/);
  assert.match(brief, /name withheld/);
  assert.doesNotMatch(brief, /private\.example\.org|source-a\.example\.org/);
  assert.doesNotMatch(brief, /secret-passphrase/);
  assert.doesNotMatch(brief, /Confirmed factual claim/);
  assert.equal(formatAdvancedDecisionBrief(board), brief);
});
test('brief refuses forged release claims or unbounded arrays', () => {
  const board = make();
  assert.throws(() => formatAdvancedDecisionBrief({
    ...board, externalReleaseAuthorized: true,
  }), /brief provenance/);
  assert.throws(() => formatAdvancedDecisionBrief({
    ...board, objectiveDecisions: Array(9).fill(board.objectiveDecisions[0]),
  }), /brief provenance/);
});
test('decision cockpit is part of actual authenticated Atlas UI and share rechecks authority', () => {
  const ui = readFileSync(resolve(ROOT,
    'src/features/Jeeves/DragonResearchDecisionCockpit.tsx'), 'utf8');
  const atlas = readFileSync(resolve(ROOT,
    'src/features/Jeeves/CrawlerResearchAtlasPanel.tsx'), 'utf8');
  assert.match(atlas, /<DragonResearchDecisionCockpit/);
  assert.match(ui, /getCrawl\(current\.session\.session_id, abort\.signal\)/);
  assert.match(ui, /requireCurrentPilotSnapshot\(witness, current\.session, latest, current\.report\)/);
  assert.match(ui, /Share\.share/);
  assert.match(ui, /setScenarioHost\(item\.removed_host\)/);
  assert.match(ui, /setReviewBudget/);
  assert.match(ui, /setPerTaskMinutes/);
  assert.match(ui, /human-review/);
  assert.ok(ui.indexOf('requireCurrentPilotSnapshot(witness, current.session, latest, current.report)')
    < ui.indexOf('await Share.share('));
});

/**
 * Dragon Advanced Research Decision Engine
 *
 * This module is deliberately a deterministic, offline-only projection over
 * the already authenticated, policy-fenced Atlas response. It cannot fetch,
 * approve, mutate, rerank, train, generate factual claims or dispatch work.
 * Observed hosts, exact-content families and lexical similarity are NOT
 * independent attestation. All tasks remain human-review-only.
 */
import type {
  CrawlAtlasObjective, CrawlAtlasReport, CrawlAtlasReviewTask, CrawlSession,
} from '../../product/crawlerClient';

export type DecisionSeverity = 'critical' | 'high' | 'review';
export type DecisionReason =
  | 'no_selected_evidence' | 'host_concentration' | 'host_loss'
  | 'possible_content_mirror' | 'source_family_shortfall'
  | 'query_unsupported' | 'source_policy_excluded'
  | 'security_forensic_hold' | 'review_not_attested';

export type ObjectiveDecision = Readonly<{
  objectiveId: string;
  dimension: string;
  stage: string;
  priority: number;
  severity: DecisionSeverity;
  reasons: DecisionReason[];
  selectedPassages: number;
  observedSources: number;
  observedHosts: number;
  distinctContentFamilies: number;
  targetPassages: number | null;
  targetAttestedGroups: number;
  apparentPassageDeficit: number | null;
  independentGroupsVerified: 0;
  hypotheticalHostLost: boolean;
  lostAllEvidenceUnderScenario: boolean;
  scenarioHostCountDropsToOne: boolean;
  nearDuplicateClusters: number;
  reviewTaskCount: number;
}>;

export type ReviewDecision = Readonly<{
  taskId: string;
  type: string;
  objectiveId: string | null;
  priority: number;
  estimatedMinutes: number;
  status: 'budgeted_now' | 'ready_but_unbudgeted' | 'dependency_held';
  predecessorCount: number;
  risk: 'critical' | 'high' | 'medium' | 'low' | 'unclassified';
  humanApprovalRequired: true;
  actionExecuted: false;
}>;

export type AdvancedDecisionBoard = Readonly<{
  schema: 'skeleton.dragon.advanced_decision_board.v1';
  sessionId: string;
  sessionVersion: number;
  atlasDigest: string;
  snapshotDigest: string;
  qualificationDigest: string;
  scenarioHost: string | null;
  objectiveCount: number;
  criticalObjectives: number;
  highObjectives: number;
  sourcePolicyIncluded: number;
  sourcePolicyExcluded: number;
  observedHosts: number;
  observedPassages: number;
  sourceFamilies: number;
  suspectedMirrors: number;
  unresolvedRobotsOrigins: number;
  pendingDispatch: boolean;
  uncertainBytes: number;
  estimatedReviewBudgetMinutes: number;
  estimatedReviewMinutesPerTask: number;
  budgetUsedMinutes: number;
  budgetedTasks: number;
  heldTasks: number;
  unlistedTasks: number;
  reviewActionableWithoutDependencies: number;
  objectiveDecisions: ObjectiveDecision[];
  reviewDecisions: ReviewDecision[];
  externalReleaseAuthorized: false;
  factualVerificationEstablished: false;
  independentSourceAttestationEstablished: false;
  networkCalled: false;
  persisted: false;
  humanReviewRequired: true;
}>;

const HASH = /^[a-f0-9]{64}$/;
const OBJECTIVE = /^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$/;
const TASK = /^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$/;
const RANK = { critical: 0, high: 1, medium: 2, low: 3, unclassified: 4 } as const;
const SEVERITY = { critical: 0, high: 1, review: 2 } as const;

function bounded(value: unknown, low: number, high: number): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value)
    && value >= low && value <= high;
}
function requireCondition(yes: unknown, reason: string): asserts yes {
  if (!yes) throw new RangeError('Unqualified Dragon decision input: ' + reason);
}
function canonicalCode(value: unknown, max = 128): string {
  requireCondition(typeof value === 'string'
    && value.length <= max && TASK.test(value), 'unexpected identifier');
  return value as string;
}
function taskRisk(
  report: CrawlAtlasReport, taskId: string,
): ReviewDecision['risk'] {
  return report.forensics.review_queue.find(row => row.task_id === taskId)?.risk
    ?? 'unclassified';
}
function sortReview(a: CrawlAtlasReviewTask, b: CrawlAtlasReviewTask,
  report: CrawlAtlasReport): number {
  const riskA = taskRisk(report, a.task_id);
  const riskB = taskRisk(report, b.task_id);
  return RANK[riskA] - RANK[riskB] || b.priority - a.priority
    || a.task_id.localeCompare(b.task_id);
}
export function buildAdvancedDecisionBoard(
  report: CrawlAtlasReport,
  session: CrawlSession,
  campaign: readonly CrawlAtlasObjective[] = [],
  scenarioHost: string | null = null,
  reviewBudgetMinutes = 90,
  reviewMinutesPerTask = 12,
): AdvancedDecisionBoard {
  // Every call is separately bound to the authenticated exact session and
  // validated Atlas receipt. Never derive from stored, pasted or partial JSON.
  requireCondition(!!report && !!session && report.session_id === session.session_id
    && session.consent_current === true && bounded(session.version, 1, 2**31 - 1),
  'session ownership or consent');
  const pilot = report.pilot_qualification;
  requireCondition(!!pilot
    && pilot.schema_version === 'skeleton.dragon.campaign_pilot_qualification.v1'
    && pilot.source_only === true && pilot.read_only === true
    && pilot.training_authorized === false && pilot.publication_authorized === false
    && pilot.release_authorized === false
    && pilot.recheck_mongo_authority_before_any_followup === true
    && report.read_only === true && report.network_executed === false
    && report.publication_granted === false && report.training_permission === false
    && report.review_required === true
    && pilot.atlas_digest === report.atlas_digest
    && pilot.snapshot_digest === report.snapshot_digest
    && pilot.source_policy_digest === report.source_policy?.digest
    && pilot.run_sequence === report.run_sequence
    && HASH.test(pilot.qualification_digest)
    && HASH.test(report.atlas_digest)
    && HASH.test(report.snapshot_digest),
  'source-only Atlas receipt / release authority');
  requireCondition(bounded(reviewBudgetMinutes, 15, 480)
    && bounded(reviewMinutesPerTask, 5, 120), 'review simulation budget');
  requireCondition(Array.isArray(report.objectives) && report.objectives.length <= 8
    && Array.isArray(report.retrieval_robustness?.objectives)
    && report.retrieval_robustness.objectives.length === report.objectives.length
    && Array.isArray(report.evidence_family_stress?.objectives)
    && report.evidence_family_stress.objectives.length === report.objectives.length
    && Array.isArray(report.evidence_graph?.objective_neighborhoods)
    && Array.isArray(report.forensics?.review_queue)
    && Array.isArray(report.review_operations?.recommended_queue)
    && Array.isArray(report.review_operations?.ready_task_ids)
    && Array.isArray(report.retrieval_robustness.host_ablation)
    && report.review_operations.recommended_queue.length <= 256,
  'bounded evidence and review structure');
  requireCondition(report.source_policy.included_source_count
    + report.source_policy.excluded_source_count === report.source_policy.sources_seen,
  'source-policy accounting');
  const chosen = scenarioHost === null ? null
    : report.retrieval_robustness.host_ablation.find(row => row.removed_host === scenarioHost);
  requireCondition(scenarioHost === null || !!chosen, 'unknown host-loss scenario');
  const goals = new Map<string, CrawlAtlasObjective>();
  requireCondition(Array.isArray(campaign) && campaign.length <= 8, 'objective count');
  for (const goal of campaign) {
    requireCondition(OBJECTIVE.test(goal.objective_id)
      && !goals.has(goal.objective_id), 'duplicate campaign objective');
    goals.set(goal.objective_id, goal);
  }
  const robust = new Map(report.retrieval_robustness.objectives.map(row =>
    [row.objective_id, row] as const));
  const stress = new Map(report.evidence_family_stress.objectives.map(row =>
    [row.objective_id, row] as const));
  const graph = new Map(report.evidence_graph.objective_neighborhoods.map(row =>
    [row.objective_id, row] as const));
  const decisions: ObjectiveDecision[] = [];
  const objectiveIds = new Set<string>();
  for (const objective of report.objectives) {
    const id = canonicalCode(objective.objective_id, 64);
    requireCondition(!objectiveIds.has(id), 'duplicate returned objective');
    objectiveIds.add(id);
    const observation = robust.get(id);
    const family = stress.get(id);
    const neighborhood = graph.get(id);
    requireCondition(!!observation && !!family && !!neighborhood,
      'incomplete per-objective evidence');
    requireCondition(bounded(observation.selected_passages, 0, 32)
      && bounded(observation.distinct_selected_sources, 0, 64)
      && bounded(observation.distinct_selected_hosts, 0, 32)
      && bounded(observation.distinct_content_families, 0, 32)
      && bounded(family.possible_near_duplicate_clusters, 0, 32)
      && bounded(family.hypothetical_target_shortfall, 0, 16)
      && bounded(neighborhood.source_count, 0, 64),
    'invalid observed evidence bounds');
    const goal = goals.get(id);
    const targetPassages = goal?.minimum_reviewable_passages ?? null;
    const targetGroups = goal?.minimum_attested_groups
      ?? family.target_attested_groups;
    requireCondition(bounded(targetGroups, 1, 16)
      && (targetPassages === null || bounded(targetPassages, 1, 32)),
    'invalid attestation target');
    const lostAllEvidence = chosen?.objectives_without_evidence.includes(id) ?? false;
    const oneHostAfterLoss = chosen?.objectives_left_with_one_host.includes(id) ?? false;
    const reasons: DecisionReason[] = [];
    if (observation.selected_passages === 0) reasons.push('no_selected_evidence');
    if (observation.risk === 'single_host' || observation.risk === 'host_concentrated') {
      reasons.push('host_concentration');
    }
    if (lostAllEvidence || oneHostAfterLoss) reasons.push('host_loss');
    if (observation.cross_host_exact_content_reuse
      || family.possible_near_duplicate_clusters > 0) reasons.push('possible_content_mirror');
    if (family.hypothetical_target_shortfall > 0) reasons.push('source_family_shortfall');
    if (report.forensics.query_unsupported_objectives > 0
      && report.retrieval_robustness.flagged_objectives.includes(id)) {
      reasons.push('query_unsupported');
    }
    if (report.source_policy.excluded_source_count > 0) reasons.push('source_policy_excluded');
    if (report.forensics.security_held_sources > 0
      || report.forensics.privacy_held_sources > 0) reasons.push('security_forensic_hold');
    if (!reasons.length) reasons.push('review_not_attested');
    const critical = observation.selected_passages === 0 || lostAllEvidence;
    const high = reasons.some(reason => reason !== 'review_not_attested');
    const severity: DecisionSeverity = critical ? 'critical'
      : high ? 'high' : 'review';
    const reviewTaskCount = report.review_operations.recommended_queue.filter(
      item => item.objective_id === id,
    ).length + report.forensics.review_queue.filter(
      item => item.objective_ids.includes(id),
    ).length;
    decisions.push(Object.freeze({
      objectiveId: id,
      dimension: objective.dimension,
      stage: objective.stage,
      priority: objective.priority,
      severity,
      reasons,
      selectedPassages: observation.selected_passages,
      observedSources: observation.distinct_selected_sources,
      observedHosts: observation.distinct_selected_hosts,
      distinctContentFamilies: observation.distinct_content_families,
      targetPassages,
      targetAttestedGroups: targetGroups,
      apparentPassageDeficit: targetPassages === null ? null
        : Math.max(0, targetPassages - observation.selected_passages),
      independentGroupsVerified: 0 as const,
      hypotheticalHostLost: scenarioHost !== null,
      lostAllEvidenceUnderScenario: lostAllEvidence,
      scenarioHostCountDropsToOne: oneHostAfterLoss,
      nearDuplicateClusters: family.possible_near_duplicate_clusters,
      reviewTaskCount,
    }));
  }
  decisions.sort((a, b) => SEVERITY[a.severity] - SEVERITY[b.severity]
    || b.priority - a.priority || a.objectiveId.localeCompare(b.objectiveId));

  const reviewedTasks = report.review_operations.recommended_queue;
  const seen = new Set<string>();
  for (const item of reviewedTasks) {
    const id = canonicalCode(item.task_id);
    requireCondition(!seen.has(id), 'duplicate review task');
    seen.add(id);
    requireCondition(Array.isArray(item.predecessors)
      && item.predecessors.length <= 256
      && Number.isFinite(item.priority)
      && item.priority >= 0 && item.priority <= 1,
    'review priority bounds');
  }
  const readyIds = new Set(report.review_operations.ready_task_ids);
  const orderedTasks = [...reviewedTasks].sort((a, b) => sortReview(a, b, report));
  const reviewDecisions: ReviewDecision[] = [];
  let used = 0;
  for (const item of orderedTasks) {
    const ready = readyIds.has(item.task_id) && item.predecessors.length === 0;
    const budgeted = ready && used + reviewMinutesPerTask <= reviewBudgetMinutes;
    if (budgeted) used += reviewMinutesPerTask;
    reviewDecisions.push(Object.freeze({
      taskId: item.task_id,
      type: canonicalCode(item.type),
      objectiveId: item.objective_id === null
        ? null : canonicalCode(item.objective_id, 64),
      priority: item.priority,
      estimatedMinutes: reviewMinutesPerTask,
      status: !ready ? 'dependency_held'
        : budgeted ? 'budgeted_now' : 'ready_but_unbudgeted',
      predecessorCount: item.predecessors.length,
      risk: taskRisk(report, item.task_id),
      humanApprovalRequired: true as const,
      actionExecuted: false as const,
    }));
  }
  return Object.freeze({
    schema: 'skeleton.dragon.advanced_decision_board.v1' as const,
    sessionId: session.session_id,
    sessionVersion: session.version,
    atlasDigest: report.atlas_digest,
    snapshotDigest: report.snapshot_digest,
    qualificationDigest: pilot.qualification_digest,
    scenarioHost,
    objectiveCount: decisions.length,
    criticalObjectives: decisions.filter(x => x.severity === 'critical').length,
    highObjectives: decisions.filter(x => x.severity === 'high').length,
    sourcePolicyIncluded: report.source_policy.included_source_count,
    sourcePolicyExcluded: report.source_policy.excluded_source_count,
    observedHosts: report.retrieval_robustness.selected_hosts,
    observedPassages: report.retrieval_robustness.selected_passages,
    sourceFamilies: report.retrieval_robustness.distinct_content_families,
    suspectedMirrors: report.source_similarity.candidate_pairs,
    unresolvedRobotsOrigins: report.operations.unresolved_robots_origins,
    pendingDispatch: report.operations.pending_dispatch,
    uncertainBytes: report.operations.uncertain_bytes,
    estimatedReviewBudgetMinutes: reviewBudgetMinutes,
    estimatedReviewMinutesPerTask: reviewMinutesPerTask,
    budgetUsedMinutes: used,
    budgetedTasks: reviewDecisions.filter(x => x.status === 'budgeted_now').length,
    heldTasks: reviewDecisions.filter(x => x.status === 'dependency_held').length,
    unlistedTasks: Math.max(0, report.review_operations.tasks_total - reviewedTasks.length),
    reviewActionableWithoutDependencies: reviewDecisions.filter(
      x => x.status !== 'dependency_held',
    ).length,
    objectiveDecisions: decisions,
    reviewDecisions,
    externalReleaseAuthorized: false as const,
    factualVerificationEstablished: false as const,
    independentSourceAttestationEstablished: false as const,
    networkCalled: false as const,
    persisted: false as const,
    humanReviewRequired: true as const,
  });
}

/** Strictly bounded, provenance-only text. No URLs, source bodies or queries. */
export function formatAdvancedDecisionBrief(board: AdvancedDecisionBoard): string {
  requireCondition(board.schema === 'skeleton.dragon.advanced_decision_board.v1'
    && board.externalReleaseAuthorized === false
    && board.humanReviewRequired === true
    && board.networkCalled === false
    && board.persisted === false
    && HASH.test(board.atlasDigest) && HASH.test(board.qualificationDigest)
    && bounded(board.sessionVersion, 1, 2**31 - 1)
    && Array.isArray(board.objectiveDecisions)
    && board.objectiveDecisions.length <= 8
    && Array.isArray(board.reviewDecisions)
    && board.reviewDecisions.length <= 256, 'brief provenance');
  const rows: string[] = [
    'DRAGON RESEARCH - ADVANCED HUMAN DECISION BRIEF',
    'READ ONLY / HISTORICAL CAPTURE / SOURCE RIGHTS REQUIRE REVALIDATION',
    'Factual accuracy: NOT VERIFIED',
    'Independent source attestation: NOT VERIFIED',
    'Approval / publication / training / launch: NOT AUTHORIZED',
    'Owner-scoped session revision: ' + board.sessionVersion,
    'Atlas: ' + board.atlasDigest.slice(0, 20),
    'Pilot receipt: ' + board.qualificationDigest.slice(0, 20),
    'Observed source passages: ' + board.observedPassages,
    'Source records held by policy: ' + board.sourcePolicyExcluded,
    'Observed host count: ' + board.observedHosts,
    'Distinct exact-content families: ' + board.sourceFamilies,
    'Possible similarity pairs (unverified): ' + board.suspectedMirrors,
    'Simulated host removal: ' + (board.scenarioHost ? 'one observed host (name withheld)' : 'none'),
    'Uncertain network bytes: ' + board.uncertainBytes,
    'Unresolved robots origins: ' + board.unresolvedRobotsOrigins,
    'Review capacity simulation: ' + board.budgetUsedMinutes
      + '/' + board.estimatedReviewBudgetMinutes + ' operator minutes',
    'Immediate estimated task slots: ' + board.budgetedTasks,
    'Dependency-held task slots: ' + board.heldTasks,
    'Additional unlisted review tasks: ' + board.unlistedTasks,
    'OBJECTIVE TRIAGE (not factual verification):',
  ];
  for (const row of board.objectiveDecisions) {
    rows.push(row.objectiveId + ': ' + row.severity
      + ', passages=' + row.selectedPassages
      + ', observed_hosts=' + row.observedHosts
      + ', attested_independent_groups=0'
      + ', risks=' + row.reasons.slice(0, 8).join(','));
  }
  rows.push('IMMEDIATE HUMAN-REVIEW ESTIMATES (nothing assigned):');
  for (const row of board.reviewDecisions.filter(x => x.status === 'budgeted_now').slice(0, 12)) {
    rows.push(row.taskId + ': ' + row.risk + ', ' + row.type
      + ', human_minutes=' + row.estimatedMinutes + ', not approved');
  }
  rows.push('All actions require a fresh canonical owner/source-policy check.');
  const result = rows.join('\n');
  requireCondition(result.length <= 7000, 'brief size ceiling');
  return result;
}

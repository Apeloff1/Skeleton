"""Dragon crawler campaign assurance under the existing canonical owner.

Explicitly import from an authorized application boundary. No import starts
a worker, opens a connection, writes state or grants new permission.
"""
from .contracts import (
    CampaignScope, CampaignLimits, CampaignMandate,
    ResearchCandidate, ResearchDispatch, CampaignPlan,
)
from .budget import BudgetProjection, BudgetReservation, project_budget, reserve_advisory
from .planner import build_campaign_plan
from .evidence import SourceInspection, CampaignPassage, EvidenceInspection, inspect_campaign_evidence
from .lineage import (
    SourceLink, LineageImpact, DuplicateFamily,
    validate_lineage, invalidation_closure, exact_duplicate_families,
)
from .journal import CampaignEntry, CampaignJournal
from .revisions import (
    SourceDelta, PassageDisposition, RevisionImpact, compare_research_revisions,
)
from .diagnostics import CampaignDiagnostics, measure_campaign_diagnostics
from .integration import CampaignInspection, frontier_hints, inspect_crawl_campaign
from .recovery import RecoveryAssessment, assess_campaign_recovery
from .control import CampaignControlProposal, propose_campaign_control
from .references import CitationCheck, CitationReport, verify_current_citations
from .recrawl_advisory import RefreshObservation, RefreshProposal, RefreshPortfolio, propose_adaptive_refresh
from .stopping import ResearchStopGate, decide_campaign_stop

from .objectives import ResearchObjective, ObjectivePlan, compile_objectives, objective_matches
from .claims import (
    ResearchClaim, ClaimCitation, IndependenceAttestation, ClaimAssessment,
    ClaimReviewMatrix, assess_claim_matrix,
)
from .coverage import ObjectiveCoverage, CoverageReport, measure_objective_coverage
from .temporal_diff import (
    RetainedVersion, ChangeSpan, TemporalChangeReport, TemporalSequence,
    compare_retained_versions, build_temporal_sequence,
)
from .novelty import (
    NoveltyDocument, NoveltyPair, NoveltyFamily, NoveltyReport,
    group_near_duplicates,
)
from .frontier_graph import HostFrontier, FrontierArc, FrontierTopology, analyze_frontier_topology
from .source_index import (
    IndexedPassage, EphemeralIndex, IndexedHit, IndexedSearch,
    build_ephemeral_index, search_ephemeral_index,
)
from .risk_register import CrawlRisk, CrawlRiskRegister, compile_crawl_risks
from .pressure import ResourceObservation, PressureDecision, recommend_crawl_pressure
from .mission_strategy import MissionCandidate, MissionStrategy, prioritize_unmet_research
from .review_packet import (
    PacketReference, ReviewPacket, create_review_packet, verify_review_packet,
)
from .replay_assurance import ReplayLink, ReplayAudit, audit_campaign_replay

from .contradictions import (
    Disagreement, CitationDependency, DisagreementGraph, build_disagreement_graph,
)
from .robots_audit import OriginRobots, RobotsAudit, audit_robots_state
from .workbench import DragonWorkbench, compose_dragon_workbench


# Atlas source-policy-first research pipeline. Explicit imports are inert:
# no network, persistence, worker spawning or source authority on import.
from .query_lattice import QueryVariant, QueryLattice, compile_query_lattice
from .retrieval_fusion import FusedEvidence, RetrievalFusion, fuse_retrieval
from .context_envelope import (
    EnvelopeReference, ResearchContextEnvelope, build_research_context,
)
from .source_drift import DriftEntry, SnapshotDrift, analyze_snapshot_drift
from .policy_matrix import (
    SourcePolicyDecision, SourcePolicyFinding, SourcePolicyProjection,
    project_source_policy,
)
from .independence_audit import (
    CorrelatedGroups, ClaimIndependence, IndependenceAudit, audit_independence,
)
from .frontier_allocator import (
    DispatchSlot, AllocationAdvice, allocate_frontier_advisory,
)
from .quality_scorecard import (
    QualityDimension, ResearchScorecard, measure_research_scorecard,
)
from .research_pipeline import (
    AtlasStage, DragonAtlas, compose_dragon_atlas, verify_dragon_atlas_trace,
)


from .policy_invalidation import (
    PolicyTransition, EvidenceInvalidation, PolicyInvalidation,
    assess_policy_invalidation,
)
from .retrieval_benchmark import (
    PassageJudgment, ObjectiveRetrievalMetrics, RetrievalBenchmark,
    RetrievalComparison, evaluate_fused_retrieval,
    compare_retrieval_benchmarks,
)


# Operational evidence, review, citation and model-handoff projections.
from .evidence_graph import (
    EvidenceVertex, EvidenceArc, ObjectiveNeighborhood, GraphIntegrity,
    EvidenceGraph, assemble_evidence_graph,
)
from .review_agenda import ReviewTask, ReviewAgenda, compile_review_agenda
from .review_replay import (
    HumanReviewAction, HumanReviewProposal, ReviewTaskState, ReviewReplay,
    replay_human_reviews, next_review_action,
)
from .research_handoff import (
    HandoffCitation, HandoffTask, ResearchHandoff,
    compile_research_handoff, verify_research_handoff,
)
from .review_portfolio import (
    ReviewEffort, PortfolioAssignment, ReviewPortfolio, allocate_human_review,
)
from .citation_manifest import (
    BoundedCitation, CitationManifest, build_citation_manifest,
    verify_citation_manifest,
)


# Lexical research intelligence: optional source-only BM25 and human review.
from .lexical_ranking import (
    LexicalRankingWeights, PassageScore, LexicalRankingReport,
    rank_ephemeral_research, lexical_report_to_fusion,
)
from .lexical_feedback import (
    FeedbackTermCandidate, ObjectiveFeedback, FeedbackReport,
    propose_reviewed_query_terms,
)
from .numeric_signals import (
    NumericMention, NumericDiscrepancy, NumericSignalReport,
    inspect_numeric_discrepancies,
)
from .temporal_signals import (
    TemporalMention, TemporalNeighborhood, TemporalSignalReport,
    detect_temporal_mentions,
)


# Canonical crawler frontier and dispatch-recovery read-only operational analysis.
from .frontier_route_map import (
    CanonicalRouteNode, CanonicalRouteArc, HostRouteLoad,
    CrawlRouteTopology, project_canonical_routes,
)
from .slice_simulation import (
    HypotheticalSliceStep, HypotheticalSlicePlan,
    simulate_canonical_slice,
)
from .dispatch_faults import (
    DispatchEventReceipt, HostFaultPressure, RecoveryStep,
    DispatchFaultLedger, analyze_dispatch_faults,
)

from .retrieval_robustness import (
    ObjectiveExposure, HostRemovalScenario, ObjectiveSourceReuse,
    RetrievalRobustnessAudit, analyze_retrieval_robustness,
)

from .near_duplicate_audit import (
    LexicalSimilarityCandidate, SimilarityComponent, SourceSimilarityAudit,
    inspect_selected_source_similarity,
)

from .evidence_family_stress import (
    ObjectiveFamilyStress, EvidenceFamilyStress,
    stress_test_evidence_families,
)

from .forensics import AtlasForensics, compose_atlas_forensics, verify_atlas_forensics

# Six-stage source-bound operational safety and replay qualification.
from .ops_timeline import TimelineEvent, OperationalTimeline, inspect_operational_timeline
from .ops_host_governor import OriginGuard, HostGovernor, govern_canonical_origins
from .ops_recovery import RecoveryWitness, RecoveryHandshake, assess_restart_handshake
from .ops_capacity import CapacityEnvelope, recommend_ops_capacity
from .ops_dispatch_envelope import ProposedWorkFingerprint, DispatchEnvelope, prepare_dispatch_envelope
from .ops_runbook import OperatorRunbookStep, OperatorRunbook, compile_operator_runbook
from .ops_plane import OperationalStage, OperationalAssurance, compose_operational_assurance, verify_operational_assurance

__all__ = [name for name in globals() if not name.startswith("_")]

"""Dragon Atlas: end-to-end bounded research inspection over canonical CrawlRun.

The Atlas is a synchronous, deterministic advisory projection. It never
fetches, starts a crawler, updates Mongo, authorizes agents, trains a model or
promotes external text to knowledge. Its source-use policy must be supplied
by an already authenticated application boundary and must cover every source
in the current canonical snapshot before any retained text is examined.

Pipeline:
  mandate -> canonical snapshot -> complete source policy -> workbench
  -> query lattice -> current-source lexical index -> diverse rank fusion
  -> exact-span context envelope -> independence audit -> resource fairness
  -> evidence scorecard -> immutable stage receipt chain -> human review.

All external mutations, acquisition, writes, licenses, independent review,
publication and rollback require separate existing application authorities.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from ..operations import CrawlRun
from .claims import ClaimCitation, IndependenceAttestation, ResearchClaim
from .contracts import CampaignMandate, digest, ensure_snapshot_scope, integer
from .context_envelope import ResearchContextEnvelope, build_research_context
from .frontier_allocator import AllocationAdvice, allocate_frontier_advisory
from .independence_audit import IndependenceAudit, audit_independence
from .lineage import SourceLink
from .objectives import ResearchObjective
from .policy_matrix import (
    SourcePolicyDecision, SourcePolicyProjection, project_source_policy,
)
from .pressure import (
    PressureDecision, ResourceObservation, recommend_crawl_pressure,
)
from .quality_scorecard import ResearchScorecard, measure_research_scorecard
from .query_lattice import QueryLattice, compile_query_lattice
from .retrieval_fusion import RetrievalFusion, fuse_retrieval
from .source_drift import SnapshotDrift, analyze_snapshot_drift
from .source_index import EphemeralIndex, build_ephemeral_index
from .workbench import DragonWorkbench, compose_dragon_workbench
from .lexical_ranking import (
    LexicalRankingWeights, LexicalRankingReport,
    rank_ephemeral_research, lexical_report_to_fusion,
)
from .retrieval_benchmark import PassageJudgment
from .lexical_feedback import FeedbackReport, propose_reviewed_query_terms
from .numeric_signals import NumericSignalReport, inspect_numeric_discrepancies
from .temporal_signals import TemporalSignalReport, detect_temporal_mentions
from .frontier_route_map import CrawlRouteTopology, project_canonical_routes
from .slice_simulation import HypotheticalSlicePlan, simulate_canonical_slice
from .dispatch_faults import DispatchFaultLedger, analyze_dispatch_faults
from .retrieval_robustness import RetrievalRobustnessAudit, analyze_retrieval_robustness
from .near_duplicate_audit import SourceSimilarityAudit, inspect_selected_source_similarity
from .evidence_family_stress import EvidenceFamilyStress, stress_test_evidence_families
from .evidence_graph import EvidenceGraph, assemble_evidence_graph
from .review_agenda import ReviewAgenda, compile_review_agenda
from .review_replay import ReviewReplay, replay_human_reviews
from .research_handoff import ResearchHandoff, compile_research_handoff, verify_research_handoff
from .review_portfolio import ReviewEffort, ReviewPortfolio, allocate_human_review
from .citation_manifest import (
    CitationManifest, build_citation_manifest, verify_citation_manifest,
)


STAGES = (
    "protected_source_policy",
    "canonical_research_workbench",
    "operator_query_lattice",
    "retained_source_index",
    "source_diverse_retrieval",
    "source_bound_context",
    "independence_counter_audit",
    "resource_bounded_frontier",
    "human_review_scorecard",
    "optional_checkpoint_drift",
    "policy_bound_evidence_graph",
    "dependency_review_agenda",
    "append_only_review_projection",
    "least_authority_jeeves_handoff",
    "optional_human_review_portfolio",
    "exact_span_citation_manifest",
    "optional_bm25_proximity_ranking",
    "bounded_numeric_difference_screening",
    "source_date_signal_inspection",
    "optional_operator_feedback_terms",
    "canonical_route_graph_diagnostics",
    "resource_bounded_slice_simulation",
    "dispatch_fault_and_recovery_impacts",
    "selected_evidence_host_ablation_and_reuse",
    "near_duplicate_source_provenance_screening",
    "objective_evidence_family_collapse_stress",
)


@dataclass(frozen=True)
class AtlasStage:
    ordinal: int
    name: str
    input_chain_digest: str
    receipt_digest: str
    chain_digest: str
    content_may_be_trusted: bool = False
    external_effect_committed: bool = False


@dataclass(frozen=True)
class DragonAtlas:
    run_id: str
    mandate_digest: str
    source_snapshot_digest: str
    source_sequence: int
    issued_at: float
    policies: SourcePolicyProjection
    workbench: DragonWorkbench
    lattice: QueryLattice
    index: EphemeralIndex
    retrieval: RetrievalFusion
    context: ResearchContextEnvelope
    independence: IndependenceAudit | None
    pressure: PressureDecision | None
    allocation: AllocationAdvice
    scorecard: ResearchScorecard
    drift: SnapshotDrift | None
    graph: EvidenceGraph
    agenda: ReviewAgenda
    review_replay: ReviewReplay
    handoff: ResearchHandoff
    portfolio: ReviewPortfolio | None
    citations: CitationManifest
    lexical_ranking: LexicalRankingReport | None
    numeric_signals: NumericSignalReport
    temporal_signals: TemporalSignalReport
    feedback: FeedbackReport | None
    routes: CrawlRouteTopology
    simulation: HypotheticalSlicePlan
    faults: DispatchFaultLedger
    robustness: RetrievalRobustnessAudit
    similarity: SourceSimilarityAudit
    family_stress: EvidenceFamilyStress
    retrieval_mode: str
    stages: tuple[AtlasStage, ...]
    atlas_digest: str
    operational_state: str = "human_review_required"
    remote_network_used: bool = False
    persistent_corpus_written: bool = False
    external_text_trusted: bool = False
    model_training_authorized: bool = False
    publication_authorized: bool = False
    dispatch_authorized: bool = False


def _stage_chain(
    mandate: CampaignMandate, snapshot_digest: str,
    receipts: Iterable[tuple[str, str | None]],
) -> tuple[AtlasStage, ...]:
    rows = tuple(receipts)
    if tuple(x[0] for x in rows) != STAGES:
        raise ValueError("unexpected Dragon Atlas stage order")
    chain = digest({
        "schema": "skeleton.dragon.atlas.v1",
        "mandate": mandate.fingerprint,
        "snapshot": snapshot_digest,
    })
    result = []
    for i, (name, receipt) in enumerate(rows):
        if receipt is None:
            receipt = digest({
                "absent": name, "mandate": mandate.fingerprint,
                "snapshot": snapshot_digest,
            })
        if not isinstance(receipt, str) or len(receipt) != 64 or any(
            letter not in "0123456789abcdef" for letter in receipt
        ):
            raise ValueError("invalid Atlas stage receipt digest")
        previous = chain
        chain = digest({
            "at": i, "name": name,
            "previous": previous, "receipt": receipt,
        })
        result.append(AtlasStage(i, name, previous, receipt, chain))
    return tuple(result)


def _receipts(atlas: DragonAtlas) -> tuple[tuple[str, str | None], ...]:
    return (
        ("protected_source_policy", atlas.policies.policy_digest),
        ("canonical_research_workbench", atlas.workbench.workbench_digest),
        ("operator_query_lattice", atlas.lattice.lattice_digest),
        ("retained_source_index", atlas.index.index_digest),
        ("source_diverse_retrieval", atlas.retrieval.fusion_digest),
        ("source_bound_context", atlas.context.envelope_digest),
        ("independence_counter_audit",
         atlas.independence.audit_digest if atlas.independence else None),
        ("resource_bounded_frontier", atlas.allocation.advice_digest),
        ("human_review_scorecard", atlas.scorecard.scorecard_digest),
        ("optional_checkpoint_drift", atlas.drift.drift_digest if atlas.drift else None),
        ("policy_bound_evidence_graph", atlas.graph.graph_digest),
        ("dependency_review_agenda", atlas.agenda.agenda_digest),
        ("append_only_review_projection", atlas.review_replay.replay_digest),
        ("least_authority_jeeves_handoff", atlas.handoff.handoff_digest),
        ("optional_human_review_portfolio",
         atlas.portfolio.portfolio_digest if atlas.portfolio else None),
        ("exact_span_citation_manifest", atlas.citations.manifest_digest),
        ("optional_bm25_proximity_ranking",
         atlas.lexical_ranking.ranking_digest if atlas.lexical_ranking else None),
        ("bounded_numeric_difference_screening", atlas.numeric_signals.report_digest),
        ("source_date_signal_inspection", atlas.temporal_signals.signal_digest),
        ("optional_operator_feedback_terms",
         atlas.feedback.feedback_digest if atlas.feedback else None),
        ("canonical_route_graph_diagnostics", atlas.routes.route_digest),
        ("resource_bounded_slice_simulation", atlas.simulation.simulation_digest),
        ("dispatch_fault_and_recovery_impacts", atlas.faults.ledger_digest),
        ("selected_evidence_host_ablation_and_reuse", atlas.robustness.audit_digest),
        ("near_duplicate_source_provenance_screening", atlas.similarity.audit_digest),
        ("objective_evidence_family_collapse_stress", atlas.family_stress.stress_digest),
    )


def compose_dragon_atlas(
    mandate: CampaignMandate,
    snapshot: dict[str, object],
    *,
    objectives: Iterable[ResearchObjective],
    source_policies: Iterable[SourcePolicyDecision],
    policy_snapshot_authenticated: bool,
    now: float,
    authorized: bool,
    claims: Iterable[ResearchClaim] = (),
    claim_citations: Iterable[ClaimCitation] = (),
    independence_attestations: Iterable[IndependenceAttestation] = (),
    source_links: Iterable[SourceLink] = (),
    telemetry: Iterable[ResourceObservation] = (),
    previous_snapshot: dict[str, object] | None = None,
    max_index_passages: int = 2048,
    max_retrieved_passages: int = 16,
    max_context_chars: int = 8000,
    review_effort: Iterable[ReviewEffort] = (),
    review_budget_minutes: int = 240,
    max_review_assignments: int = 32,
    retrieval_mode: str = "fusion",
    ranking_weights: LexicalRankingWeights | None = None,
    reviewed_relevance_labels: Iterable[PassageJudgment] = (),
) -> DragonAtlas:
    """Compose one immutable, review-only source-bound research snapshot.

    Caller contracts:
      - current tenant/owner, request and source policy came from protected
        authenticated backend authority, never crawler/page/LLM suggestions;
      - a later consumer *re-fetches* both snapshot and source-use policy
        before acting on any reference; this receipt cannot certify either;
      - no resource pressure observation may be invented, re-timed or treated
        as permission to spawn a worker.
    """
    mandate.admit(now=now, authorized=authorized)
    ensure_snapshot_scope(snapshot, mandate)
    integer(max_index_passages, "index capacity", 1, 4096)
    integer(max_retrieved_passages, "retrieval capacity", 1, 32)
    integer(max_context_chars, "context capacity", 512, 24_000)
    canonical = CrawlRun.from_snapshot(snapshot).snapshot()
    policy_rows = tuple(source_policies)
    objective_rows = tuple(objectives)
    claim_rows = tuple(claims)
    citation_rows = tuple(claim_citations)
    groups = tuple(independence_attestations)
    links = tuple(source_links)
    observations = tuple(telemetry)
    effort_estimates = tuple(review_effort)
    relevance_labels = tuple(reviewed_relevance_labels)
    if retrieval_mode not in ("fusion", "lexical_bm25"):
        raise ValueError("unsupported source-only retrieval algorithm")
    if ranking_weights is not None and not isinstance(ranking_weights, LexicalRankingWeights):
        raise TypeError("typed lexical ranking parameters required")
    # STOP before reading external page bodies unless ALL retained sources
    # have current, revision-accurate source-use decisions from the backend.
    policy = project_source_policy(
        mandate, canonical, policy_rows, now=now, authorized=authorized,
        policy_snapshot_authenticated=policy_snapshot_authenticated,
    )
    withdrawn = policy.excluded_source_ids
    workbench = compose_dragon_workbench(
        mandate, canonical, objectives=objective_rows,
        claims=claim_rows, claim_citations=citation_rows,
        independence_attestations=groups,
        revoked_source_ids=withdrawn,
        source_links=links,
        now=now, authorized=authorized,
    )
    lattice = compile_query_lattice(
        mandate, workbench.objectives, now=now, authorized=authorized,
    )
    index = build_ephemeral_index(
        mandate, canonical, now=now, authorized=authorized,
        revoked_source_ids=withdrawn, max_passages=max_index_passages,
    )
    if retrieval_mode == "lexical_bm25":
        lexical = rank_ephemeral_research(
            mandate, canonical, policy, index, lattice,
            now=now, authorized=authorized,
            weights=ranking_weights or LexicalRankingWeights(),
            max_results=max_retrieved_passages,
            max_context_chars=max_context_chars,
            max_receipts=8192,
        )
        fused = lexical_report_to_fusion(lexical)
    else:
        if ranking_weights is not None:
            raise ValueError("lexical scoring parameters require lexical_bm25 mode")
        lexical = None
        fused = fuse_retrieval(
            mandate, canonical, index, lattice, now=now,
            authorized=authorized, revoked_source_ids=withdrawn,
            max_results=max_retrieved_passages,
            max_context_chars=max_context_chars,
        )
    numeric = inspect_numeric_discrepancies(
        mandate, canonical, policy, fused, now=now, authorized=authorized,
    )
    temporal = detect_temporal_mentions(
        mandate, canonical, policy, fused, now=now, authorized=authorized,
    )
    feedback = (
        propose_reviewed_query_terms(
            mandate, policy, workbench.objectives, lattice, index,
            relevance_labels, now=now, authorized=authorized,
        ) if relevance_labels else None
    )
    context = build_research_context(
        mandate, canonical, fused, now=now, authorized=authorized,
        revoked_source_ids=withdrawn,
        max_context_chars=max_context_chars,
        max_references=max_retrieved_passages,
    )
    independent = (
        audit_independence(
            mandate, canonical, workbench.claim_matrix, groups,
            links=links, revoked_source_ids=withdrawn,
            now=now, authorized=authorized,
        ) if workbench.claim_matrix else None
    )
    pressure = (
        recommend_crawl_pressure(
            mandate, workbench.inspection.budget, observations,
            now=now, authorized=authorized,
        ) if observations else None
    )
    allocation = allocate_frontier_advisory(
        mandate, workbench.topology, workbench.strategy,
        workbench.inspection.budget, pressure=pressure,
        now=now, authorized=authorized,
    )
    scorecard = measure_research_scorecard(
        mandate, workbench.inspection, workbench.coverage,
        policy, fused, context, independent, now=now, authorized=authorized,
    )
    drift = (
        analyze_snapshot_drift(
            mandate, previous_snapshot, canonical, now=now,
            authorized=authorized, revoked_source_ids=withdrawn,
        ) if previous_snapshot is not None else None
    )
    graph = assemble_evidence_graph(
        mandate, canonical, policy, workbench.objectives,
        index, fused, now=now, authorized=authorized,
        claims=workbench.claim_matrix, independence=independent,
        links=links,
    )
    agenda = compile_review_agenda(
        mandate, graph, policy, fused, workbench.coverage,
        now=now, authorized=authorized,
        claims=workbench.claim_matrix, independence=independent,
    )
    # No action can be asserted as authenticated by a caller-provided page,
    # model message or browser request. The canonical reviewed-knowledge
    # owner must perform every subsequent human-authenticated transition.
    review_replay = replay_human_reviews(
        mandate, agenda, policy, (), now=now, authorized=authorized,
    )
    handoff = compile_research_handoff(
        mandate, policy, graph, fused, agenda,
        replay=review_replay, now=now, authorized=authorized,
        max_citations=max_retrieved_passages,
    )
    portfolio = (
        allocate_human_review(
            mandate, agenda, effort_estimates, replay=review_replay,
            now=now, authorized=authorized,
            budget_minutes=review_budget_minutes,
            max_assignments=max_review_assignments,
        ) if effort_estimates else None
    )
    citations = build_citation_manifest(
        mandate, canonical, policy, fused,
        now=now, authorized=authorized,
        max_citations=max_retrieved_passages,
    )
    routes = project_canonical_routes(
        mandate, canonical, now=now, authorized=authorized,
    )
    simulation = simulate_canonical_slice(
        mandate, canonical, routes, workbench.inspection.budget,
        now=now, authorized=authorized, pressure=pressure,
    )
    faults = analyze_dispatch_faults(
        mandate, canonical, workbench.inspection.budget,
        now=now, authorized=authorized,
    )
    robustness = analyze_retrieval_robustness(
        mandate, canonical, workbench.objectives, policy, fused,
        now=now, authorized=authorized,
    )
    similarity = inspect_selected_source_similarity(
        mandate, canonical, policy, fused,
        now=now, authorized=authorized,
    )
    family_stress = stress_test_evidence_families(
        mandate, canonical, workbench.objectives, policy, fused,
        robustness, similarity, now=now, authorized=authorized,
    )
    root = DragonAtlas(
        run_id=canonical["run_id"],
        mandate_digest=mandate.fingerprint,
        source_snapshot_digest=canonical["snapshot_digest"],
        source_sequence=canonical["sequence"],
        issued_at=now, policies=policy, workbench=workbench,
        lattice=lattice, index=index, retrieval=fused, context=context,
        independence=independent, pressure=pressure,
        allocation=allocation, scorecard=scorecard, drift=drift,
        graph=graph, agenda=agenda, review_replay=review_replay,
        handoff=handoff, portfolio=portfolio, citations=citations,
        lexical_ranking=lexical, numeric_signals=numeric,
        temporal_signals=temporal, feedback=feedback,
        routes=routes, simulation=simulation, faults=faults,
        robustness=robustness, similarity=similarity, family_stress=family_stress,
        retrieval_mode=retrieval_mode,
        stages=(), atlas_digest="",
    )
    stages = _stage_chain(
        mandate, canonical["snapshot_digest"], _receipts(root),
    )
    output_digest = digest({
        "mandate": mandate.fingerprint,
        "run": canonical["run_id"],
        "snapshot": canonical["snapshot_digest"],
        "sequence": canonical["sequence"],
        "at": now,
        "final_stage": stages[-1].chain_digest,
        "holds": scorecard.alerts,
        "source_policy": policy.policy_digest,
        "review_only": True,
    })
    return DragonAtlas(
        **{**root.__dict__, "stages": stages, "atlas_digest": output_digest},
    )


def verify_dragon_atlas_trace(
    mandate: CampaignMandate,
    snapshot: dict[str, object],
    atlas: DragonAtlas,
    *,
    now: float,
    authorized: bool,
) -> None:
    """Verify receipt-chain integrity; NOT authenticate the source policy."""
    mandate.admit(now=now, authorized=authorized)
    ensure_snapshot_scope(snapshot, mandate)
    if not isinstance(atlas, DragonAtlas):
        raise TypeError("typed Atlas result required")
    canonical = CrawlRun.from_snapshot(snapshot).snapshot()
    if atlas.mandate_digest != mandate.fingerprint or (
        atlas.source_snapshot_digest != canonical["snapshot_digest"]
        or atlas.run_id != canonical["run_id"]
        or atlas.source_sequence != canonical["sequence"]
    ):
        raise PermissionError("Atlas no longer bound to the current crawl")
    if atlas.issued_at > now or atlas.issued_at < mandate.created_at:
        raise ValueError("invalid Atlas receipt clock")
    if any((
        atlas.remote_network_used, atlas.persistent_corpus_written,
        atlas.external_text_trusted, atlas.model_training_authorized,
        atlas.publication_authorized, atlas.dispatch_authorized,
    )):
        raise PermissionError("Atlas cannot assert elevated authority")
    if atlas.operational_state != "human_review_required":
        raise PermissionError("unapproved Atlas operational state")
    expected = _stage_chain(
        mandate, canonical["snapshot_digest"], _receipts(atlas),
    )
    if expected != atlas.stages:
        raise ValueError("Atlas stage chain mismatch")
    payload = {
        "mandate": mandate.fingerprint,
        "run": canonical["run_id"],
        "snapshot": canonical["snapshot_digest"],
        "sequence": canonical["sequence"],
        "at": atlas.issued_at,
        "final_stage": expected[-1].chain_digest,
        "holds": atlas.scorecard.alerts,
        "source_policy": atlas.policies.policy_digest,
        "review_only": True,
    }
    if digest(payload) != atlas.atlas_digest:
        raise ValueError("Atlas digest mismatch")
    if atlas.policies.excluded_source_ids != atlas.retrieval.excluded_sources:
        raise PermissionError("Atlas withdrawal set inconsistent")
    if atlas.context.retrieval_digest != atlas.retrieval.fusion_digest:
        raise PermissionError("Atlas context attached to foreign retrieval")
    if atlas.scorecard.source_snapshot_digest != atlas.source_snapshot_digest:
        raise PermissionError("Atlas scorecard attached to foreign source")
    if atlas.graph.source_snapshot_digest != atlas.source_snapshot_digest or (
        atlas.graph.source_policy_digest != atlas.policies.policy_digest
        or atlas.graph.retrieval_digest != atlas.retrieval.fusion_digest
    ):
        raise PermissionError("Atlas graph policy or retrieval revision mismatch")
    if atlas.agenda.graph_digest != atlas.graph.graph_digest or (
        atlas.agenda.policy_digest != atlas.policies.policy_digest
        or atlas.agenda.retrieval_digest != atlas.retrieval.fusion_digest
    ):
        raise PermissionError("Atlas review agenda provenance mismatch")
    if atlas.review_replay.agenda_digest != atlas.agenda.agenda_digest or (
        atlas.review_replay.policy_digest != atlas.policies.policy_digest
    ):
        raise PermissionError("Atlas review replay has stale policy")
    if atlas.portfolio and (
        atlas.portfolio.agenda_digest != atlas.agenda.agenda_digest
        or atlas.portfolio.replay_digest != atlas.review_replay.replay_digest
    ):
        raise PermissionError("Atlas human effort portfolio is stale")
    verify_research_handoff(
        mandate, atlas.policies, atlas.graph, atlas.retrieval,
        atlas.agenda, atlas.handoff, now=now,
        authorized=authorized, replay=atlas.review_replay,
    )
    verify_citation_manifest(
        mandate, canonical, atlas.policies, atlas.retrieval,
        atlas.citations, now=now, authorized=authorized,
        max_citations=atlas.citations.max_citations,
        max_serialized_bytes=atlas.citations.max_serialized_bytes,
    )
    if atlas.retrieval_mode not in ("fusion", "lexical_bm25"):
        raise PermissionError("Atlas advertises an unknown retrieval algorithm")
    if atlas.retrieval_mode == "fusion" and atlas.lexical_ranking is not None:
        raise PermissionError("reciprocal fusion cannot claim BM25 scoring")
    if atlas.retrieval_mode == "lexical_bm25":
        if not atlas.lexical_ranking or (
            lexical_report_to_fusion(atlas.lexical_ranking) != atlas.retrieval
        ):
            raise PermissionError("Atlas BM25 ranking receipt not bound to retrieved passages")
    for report, field in (
        (atlas.numeric_signals, "report_digest"),
        (atlas.temporal_signals, "signal_digest"),
    ):
        if (
            report.mandate_digest != mandate.fingerprint
            or report.source_snapshot_digest != atlas.source_snapshot_digest
            or report.source_policy_digest != atlas.policies.policy_digest
            or report.retrieval_digest != atlas.retrieval.fusion_digest
        ):
            raise PermissionError("source-analysis report not bound to Atlas evidence")
    if atlas.feedback is not None and (
        atlas.feedback.mandate_digest != mandate.fingerprint
        or atlas.feedback.source_snapshot_digest != atlas.source_snapshot_digest
        or atlas.feedback.policy_digest != atlas.policies.policy_digest
        or atlas.feedback.query_lattice_digest != atlas.lattice.lattice_digest
    ):
        raise PermissionError("Atlas human-feedback projection references stale sources")
    if (
        atlas.routes.mandate_digest != mandate.fingerprint
        or atlas.routes.source_snapshot_digest != atlas.source_snapshot_digest
        or atlas.routes.run_id != atlas.run_id
        or atlas.simulation.mandate_digest != mandate.fingerprint
        or atlas.simulation.source_snapshot_digest != atlas.source_snapshot_digest
        or atlas.simulation.routes_digest != atlas.routes.route_digest
        or atlas.faults.mandate_digest != mandate.fingerprint
        or atlas.faults.source_snapshot_digest != atlas.source_snapshot_digest
        or atlas.faults.run_id != atlas.run_id
        or atlas.faults.source_sequence != atlas.source_sequence
    ):
        raise PermissionError("Atlas operations receipt mismatch")
    if (
        atlas.simulation.actual_network_executed
        or atlas.simulation.reservation_committed
        or atlas.simulation.worker_lease_authenticated
        or atlas.faults.worker_join_confirmed
        or atlas.faults.mongo_commit_confirmed
        or atlas.faults.budget_refunded
    ):
        raise PermissionError("Atlas simulated operations claim real network or Mongo authority")
    if (
        atlas.robustness.mandate_digest != mandate.fingerprint
        or atlas.robustness.source_snapshot_digest != atlas.source_snapshot_digest
        or atlas.robustness.policy_digest != atlas.policies.policy_digest
        or atlas.robustness.retrieval_digest != atlas.retrieval.fusion_digest
        or atlas.robustness.objective_plan_digest != atlas.workbench.objectives.plan_digest
        or not atlas.robustness.source_bodies_excluded
        or atlas.robustness.counterfactual_ranking_executed
        or atlas.robustness.verified_independence
        or atlas.robustness.training_authorized
        or atlas.robustness.publication_authorized
    ):
        raise PermissionError("Atlas retrieval robustness receipt claims foreign evidence or authority")
    # The robustness digest alone is not enough: reconstruct the exact
    # selected-passage provenance and ensure a forged internal scenario
    # cannot survive by retaining an earlier audit digest.
    expected_robustness = analyze_retrieval_robustness(
        mandate, canonical, atlas.workbench.objectives,
        atlas.policies, atlas.retrieval,
        now=now, authorized=authorized,
    )
    if expected_robustness != atlas.robustness:
        raise PermissionError("Atlas selected-evidence sensitivity was altered")
    if (
        atlas.similarity.mandate_digest != mandate.fingerprint
        or atlas.similarity.source_snapshot_digest != atlas.source_snapshot_digest
        or atlas.similarity.source_policy_digest != atlas.policies.policy_digest
        or atlas.similarity.retrieval_digest != atlas.retrieval.fusion_digest
        or atlas.similarity.source_body_exposed
        or atlas.similarity.external_lookup_performed
        or atlas.similarity.lineage_verified
        or atlas.similarity.factual_independence_certified
        or atlas.similarity.training_or_publication_granted
    ):
        raise PermissionError("Atlas near-duplicate report asserts unavailable source authority")
    # Recalculate all similarity edges against the original captured text;
    # a mutable digest string cannot authenticate the original pair set.
    expected_similarity = inspect_selected_source_similarity(
        mandate, canonical, atlas.policies, atlas.retrieval,
        now=now, authorized=authorized,
    )
    if expected_similarity != atlas.similarity:
        raise PermissionError("Atlas selected-source similarity was altered")
    if (
        atlas.family_stress.mandate_digest != mandate.fingerprint
        or atlas.family_stress.source_snapshot_digest != atlas.source_snapshot_digest
        or atlas.family_stress.policy_digest != atlas.policies.policy_digest
        or atlas.family_stress.retrieval_digest != atlas.retrieval.fusion_digest
        or atlas.family_stress.objective_plan_digest != atlas.workbench.objectives.plan_digest
        or atlas.family_stress.robustness_digest != atlas.robustness.audit_digest
        or atlas.family_stress.similarity_digest != atlas.similarity.audit_digest
        or atlas.family_stress.independent_sources_certified
        or atlas.family_stress.claim_correctness_verified
        or atlas.family_stress.source_text_exported
        or atlas.family_stress.model_or_network_invoked
        or not atlas.family_stress.human_review_required
    ):
        raise PermissionError("Atlas evidence-family stress exceeded source authority")
    expected_family_stress = stress_test_evidence_families(
        mandate, canonical, atlas.workbench.objectives,
        atlas.policies, atlas.retrieval, atlas.robustness,
        atlas.similarity, now=now, authorized=authorized,
    )
    if expected_family_stress != atlas.family_stress:
        raise PermissionError("Atlas evidence-family collapse scenario was altered")

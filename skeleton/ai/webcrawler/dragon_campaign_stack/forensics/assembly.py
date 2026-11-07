"""Read-only, authenticated-caller-owned Dragon Atlas forensic expansion.

Composition never examines a source unless the entire canonical Atlas trace,
source policy and retrieval anchor set were verified against the same snapshot.
The returned report intentionally contains no page-body text or FrameSet.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..contracts import CampaignMandate, digest
from ..research_pipeline import DragonAtlas, verify_dragon_atlas_trace
from .frames import bind_selected_frames
from .text_security import TextSecurityReport, scan_text_security
from .anchor_geometry import AnchorGeometry, measure_anchor_geometry
from .source_reuse import SourceReuseReport, analyze_source_reuse
from .objective_resilience import ObjectiveResilience, analyze_objective_resilience
from .boilerplate import BoilerplateReport, inspect_boilerplate
from .freshness import CaptureAgeReport, inspect_capture_age
from .review_triage import ForensicReviewQueue, compile_forensic_review_queue
from .sentence_echo import SentenceEchoReport, inspect_sentence_echoes
from .active_content import ActiveContentReport, inspect_active_content
from .privacy_signals import PrivacySignalReport, inspect_privacy_signals
from .host_exposure import HostExposureReport, measure_host_exposure
from .polarity_screen import PolarityScreen, inspect_polarity_candidates
from .provenance_posture import ProvenancePosture, audit_capture_provenance
from .objective_grounding import ObjectiveGroundingReport, inspect_objective_grounding
from .reference_concentration import CitationConcentrationReport, inspect_reference_concentration
from .consent_horizon import ConsentHorizon, inspect_consent_horizon
from .source_usage_map import SourceUsageMap, compile_source_usage_map
from .research_gap_matrix import ResearchGapMatrix, synthesize_research_gaps
from .context_budget_audit import ContextBudgetAudit, audit_context_budget
from .extraction_quality import ExtractionQualityReport, inspect_extraction_quality
from .query_support_audit import QuerySupportAudit, audit_query_support
from .source_origin_audit import SourceOriginAudit, audit_selected_origins
from .selection_fairness import SelectionFairnessAudit, measure_selection_fairness
from .risk_ablation import RiskAblationReport, simulate_risk_ablations
from .script_coverage import ScriptCoverageReport, inspect_script_coverage
from .trace import ForensicStage, ORDER, chain_forensic_receipts, verify_forensic_stage_chain


@dataclass(frozen=True)
class AtlasForensics:
    mandate_digest: str
    run_id: str
    source_snapshot_digest: str
    source_policy_digest: str
    retrieval_digest: str
    atlas_digest: str
    frame_set_digest: str
    selected_anchor_count: int
    selected_source_count: int
    security: TextSecurityReport
    geometry: AnchorGeometry
    reuse: SourceReuseReport
    resilience: ObjectiveResilience
    boilerplate: BoilerplateReport
    freshness: CaptureAgeReport
    echoes: SentenceEchoReport
    active_content: ActiveContentReport
    privacy: PrivacySignalReport
    exposure: HostExposureReport
    polarity: PolarityScreen
    provenance: ProvenancePosture
    grounding: ObjectiveGroundingReport
    reference_concentration: CitationConcentrationReport
    consent: ConsentHorizon
    usage: SourceUsageMap
    gaps: ResearchGapMatrix
    context_budget: ContextBudgetAudit
    extraction: ExtractionQualityReport
    query_support: QuerySupportAudit
    origins: SourceOriginAudit
    selection_fairness: SelectionFairnessAudit
    risk_ablation: RiskAblationReport
    script_coverage: ScriptCoverageReport
    reviews: ForensicReviewQueue
    stages: tuple[ForensicStage, ...]
    report_digest: str
    security_review_required: bool = True
    human_review_required: bool = True
    web_or_model_invoked: bool = False
    source_text_exported: bool = False
    persistent_state_written: bool = False
    factual_claims_verified: bool = False
    publication_authorized: bool = False
    new_crawl_authorized: bool = False


def _receipts(report: AtlasForensics) -> tuple[tuple[str, str], ...]:
    return tuple(zip(ORDER, (
        report.frame_set_digest,
        report.security.report_digest,
        report.geometry.report_digest,
        report.reuse.report_digest,
        report.resilience.report_digest,
        report.boilerplate.report_digest,
        report.freshness.report_digest,
        report.echoes.report_digest,
        report.active_content.report_digest,
        report.privacy.report_digest,
        report.exposure.report_digest,
        report.polarity.report_digest,
        report.provenance.posture_digest,
        report.grounding.report_digest,
        report.reference_concentration.report_digest,
        report.consent.report_digest,
        report.usage.map_digest,
        report.gaps.matrix_digest,
        report.context_budget.audit_digest,
        report.extraction.report_digest,
        report.query_support.audit_digest,
        report.origins.audit_digest,
        report.selection_fairness.audit_digest,
        report.risk_ablation.report_digest,
        report.script_coverage.report_digest,
        report.reviews.queue_digest,
    )))


def compose_atlas_forensics(
    mandate: CampaignMandate, snapshot: dict[str, object],
    atlas: DragonAtlas, *, now: float, authorized: bool,
) -> AtlasForensics:
    """Build twenty-six bounded, deterministic source-fenced review projections."""
    verify_dragon_atlas_trace(
        mandate, snapshot, atlas, now=now, authorized=authorized,
    )
    frames = bind_selected_frames(
        mandate, snapshot, atlas.policies, atlas.retrieval,
        now=now, authorized=authorized,
    )
    security = scan_text_security(frames)
    geometry = measure_anchor_geometry(frames)
    reuse = analyze_source_reuse(frames, atlas.similarity)
    resilience = analyze_objective_resilience(
        frames, atlas.workbench.objectives, reuse,
    )
    boilerplate = inspect_boilerplate(frames)
    age = inspect_capture_age(
        mandate, snapshot, frames, atlas.workbench.objectives,
        now=now, authorized=authorized,
    )
    echoes = inspect_sentence_echoes(frames)
    active = inspect_active_content(frames)
    privacy = inspect_privacy_signals(frames)
    exposure = measure_host_exposure(frames, atlas.workbench.objectives)
    polarity = inspect_polarity_candidates(frames)
    provenance = audit_capture_provenance(
        mandate, snapshot, frames, now=now, authorized=authorized,
    )
    grounding = inspect_objective_grounding(
        frames, atlas.workbench.objectives,
    )
    concentration = inspect_reference_concentration(frames)
    consent = inspect_consent_horizon(
        mandate, frames, now=now, authorized=authorized,
    )
    usage = compile_source_usage_map(
        frames, atlas.workbench.objectives,
    )
    gaps = synthesize_research_gaps(
        frames, atlas.workbench.objectives, grounding, resilience,
        exposure, provenance, usage,
    )
    context_budget = audit_context_budget(mandate, frames)
    extraction = inspect_extraction_quality(frames)
    query_support = audit_query_support(
        frames, atlas.lattice, atlas.retrieval,
    )
    origins = audit_selected_origins(
        mandate, snapshot, frames, now=now, authorized=authorized,
    )
    selection_fairness = measure_selection_fairness(
        frames, atlas.workbench.objectives,
    )
    risk_ablation = simulate_risk_ablations(
        frames, atlas.workbench.objectives,
        security, privacy, active, extraction, origins,
    )
    script_coverage = inspect_script_coverage(
        frames, atlas.workbench.objectives,
    )
    reviews = compile_forensic_review_queue(
        frames, security, geometry, reuse, resilience, boilerplate, age,
        echoes=echoes, active=active, privacy=privacy,
        exposure=exposure, polarity=polarity,
        provenance=provenance, grounding=grounding,
        concentration=concentration, consent=consent,
        usage=usage, gaps=gaps, context_budget=context_budget,
        extraction=extraction, query_support=query_support,
        origins=origins, selection_fairness=selection_fairness,
        risk_ablation=risk_ablation, script_coverage=script_coverage,
    )
    root = AtlasForensics(
        mandate.fingerprint, atlas.run_id, atlas.source_snapshot_digest,
        atlas.policies.policy_digest, atlas.retrieval.fusion_digest,
        atlas.atlas_digest, frames.frame_set_digest,
        len(frames.frames), len(reuse.selected_sources), security, geometry,
        reuse, resilience, boilerplate, age, echoes, active, privacy,
        exposure, polarity, provenance, grounding, concentration, consent,
        usage, gaps, context_budget, extraction, query_support,
        origins, selection_fairness, risk_ablation, script_coverage,
        reviews, (), "",
    )
    stages = chain_forensic_receipts(
        root.mandate_digest, root.source_snapshot_digest,
        root.source_policy_digest, _receipts(root),
    )
    seal = digest({
        "schema": "skeleton.dragon.forensics.v1",
        "mandate": root.mandate_digest,
        "run": root.run_id,
        "snapshot": root.source_snapshot_digest,
        "policy": root.source_policy_digest,
        "retrieval": root.retrieval_digest,
        "atlas": root.atlas_digest,
        "anchors": root.selected_anchor_count,
        "sources": root.selected_source_count,
        "chain": stages[-1].chain_digest,
        "human_review_only": True,
    })
    return AtlasForensics(**{
        **root.__dict__, "stages": stages, "report_digest": seal,
    })


def verify_atlas_forensics(
    mandate: CampaignMandate, snapshot: dict[str, object],
    atlas: DragonAtlas, report: AtlasForensics,
    *, now: float, authorized: bool,
) -> None:
    """Rebuild from current canonical source text; never trust caller digests."""
    if not isinstance(report, AtlasForensics):
        raise TypeError("typed forensic report required")
    if any((report.web_or_model_invoked, report.source_text_exported,
            report.persistent_state_written, report.factual_claims_verified,
            report.publication_authorized, report.new_crawl_authorized)):
        raise PermissionError("forensic report attempts to grant execution or knowledge")
    if not report.human_review_required or not report.security_review_required:
        raise PermissionError("forensic report falsely asserts review completion")
    verify_forensic_stage_chain(
        report.stages, report.mandate_digest, report.source_snapshot_digest,
        report.source_policy_digest, _receipts(report),
    )
    expected = compose_atlas_forensics(
        mandate, snapshot, atlas, now=now, authorized=authorized,
    )
    if expected != report:
        raise PermissionError("forensic source, policy, result or receipt was altered")

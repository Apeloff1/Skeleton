"""Finite, stable forensic human-review queue without content or authority leaks.

Tasks are only metadata leads. A person must inspect authenticated current
policy/source evidence in the existing reviewed-knowledge application. These
tasks are not a decision, signature or request to invoke a model or crawler.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from ..contracts import digest
from .frames import FrameSet
from .text_security import TextSecurityReport
from .anchor_geometry import AnchorGeometry
from .source_reuse import SourceReuseReport
from .objective_resilience import ObjectiveResilience
from .boilerplate import BoilerplateReport
from .freshness import CaptureAgeReport
from .sentence_echo import SentenceEchoReport
from .active_content import ActiveContentReport
from .privacy_signals import PrivacySignalReport
from .host_exposure import HostExposureReport
from .polarity_screen import PolarityScreen
from .provenance_posture import ProvenancePosture
from .objective_grounding import ObjectiveGroundingReport
from .reference_concentration import CitationConcentrationReport
from .consent_horizon import ConsentHorizon
from .source_usage_map import SourceUsageMap
from .research_gap_matrix import ResearchGapMatrix
from .context_budget_audit import ContextBudgetAudit
from .extraction_quality import ExtractionQualityReport
from .query_support_audit import QuerySupportAudit
from .source_origin_audit import SourceOriginAudit
from .selection_fairness import SelectionFairnessAudit
from .risk_ablation import RiskAblationReport
from .script_coverage import ScriptCoverageReport


@dataclass(frozen=True)
class ForensicReviewTask:
    task_id: str
    risk: str
    reason: str
    source_ids: tuple[str, ...]
    objective_ids: tuple[str, ...]
    source_snapshot_digest: str
    source_policy_digest: str
    task_digest: str
    model_may_decide: bool = False
    policy_mutation_authorized: bool = False


@dataclass(frozen=True)
class ForensicReviewQueue:
    frame_set_digest: str
    tasks: tuple[ForensicReviewTask, ...]
    severe_count: int
    held_source_ids: tuple[str, ...]
    held_objective_ids: tuple[str, ...]
    queue_digest: str
    human_review_required: bool = True
    automatic_publication_permitted: bool = False


def compile_forensic_review_queue(
    frames: FrameSet, security: TextSecurityReport, geometry: AnchorGeometry,
    reuse: SourceReuseReport, resilience: ObjectiveResilience,
    boilerplate: BoilerplateReport, age: CaptureAgeReport,
    *, echoes: SentenceEchoReport | None = None,
    active: ActiveContentReport | None = None,
    privacy: PrivacySignalReport | None = None,
    exposure: HostExposureReport | None = None,
    polarity: PolarityScreen | None = None,
    provenance: ProvenancePosture | None = None,
    grounding: ObjectiveGroundingReport | None = None,
    concentration: CitationConcentrationReport | None = None,
    consent: ConsentHorizon | None = None,
    usage: SourceUsageMap | None = None,
    gaps: ResearchGapMatrix | None = None,
    context_budget: ContextBudgetAudit | None = None,
    extraction: ExtractionQualityReport | None = None,
    query_support: QuerySupportAudit | None = None,
    origins: SourceOriginAudit | None = None,
    selection_fairness: SelectionFairnessAudit | None = None,
    risk_ablation: RiskAblationReport | None = None,
    script_coverage: ScriptCoverageReport | None = None,
    max_tasks: int = 256,
) -> ForensicReviewQueue:
    from ..contracts import integer
    integer(max_tasks, "review task count", 1, 256)
    if any(x != frames.frame_set_digest for x in (
        security.frame_set_digest, geometry.frame_set_digest,
        reuse.frame_set_digest, resilience.frame_set_digest,
        boilerplate.frame_set_digest, age.frame_set_digest,
    )):
        raise PermissionError("forensic review inputs come from different source projections")
    signals: set[tuple[str, str, tuple[str, ...], tuple[str, ...]]] = set()
    def add(risk: str, reason: str, sources=(), goals=()) -> None:
        signals.add((risk, reason, tuple(sorted(set(sources))), tuple(sorted(set(goals)))))
    for finding in security.findings:
        for reason in finding.rule_codes:
            add("critical" if reason in ("tool_exfiltration", "instruction_override",
                  "role_spoof", "tool_invocation") else "high",
                "text_integrity:" + reason, (finding.source_id,))
    for row in geometry.by_source:
        if row.duplicate_region_review:
            add("medium", "overlapping_source_passages", (row.source_id,), row.objective_ids)
    for component in reuse.components:
        add("high" if len(component.hosts) > 1 else "medium",
            "source_copy_provenance_unverified", component.source_ids)
    for row in resilience.objectives:
        if not row.selected_sources:
            add("high", "no_selected_evidence", (), (row.objective_id,))
        elif row.hypothetical_family_shortfall:
            add("high", "potential_correlated_evidence", (), (row.objective_id,))
        if row.surviving_sources_after_worst_host_loss == 0 and row.selected_sources:
            add("medium", "host_single_point_of_failure", (), (row.objective_id,))
    for row in boilerplate.findings:
        if row.high_repetition_review or row.low_diversity_review:
            add("medium", "low_information_or_repetitive_text", (row.source_id,))
    for row in age.findings:
        if row.stale_capture_ids:
            add("high", "source_capture_age_exceeded", row.stale_capture_ids, (row.objective_id,))
        if row.unknown_capture_ids:
            add("high", "source_capture_time_unverified", row.unknown_capture_ids, (row.objective_id,))
    # Extension inputs must be anchored to the same exact private frame set.
    for item in (echoes, active, privacy, exposure, polarity):
        if item is not None and item.frame_set_digest != frames.frame_set_digest:
            raise PermissionError("deep forensic findings reference foreign evidence")
    if echoes:
        for row in echoes.echoes:
            add("high" if row.cross_host else "medium",
                "repeated_sentence_provenance_unverified", row.source_ids)
    if active:
        for row in active.findings:
            for code in row.rule_codes:
                add("high", "active_content:" + code, (row.source_id,))
    if privacy:
        for row in privacy.findings:
            for code in row.rule_codes:
                add("critical", "privacy_or_credential:" + code, (row.source_id,))
    if exposure:
        for row in exposure.by_objective:
            if row.objective_id in exposure.concentration_review_objectives:
                add("medium", "host_selection_concentration", (), (row.objective_id,))
    if polarity:
        for row in polarity.leads:
            add("medium", "possible_statement_polarity_collision",
                (row.left_source_id, row.right_source_id))
    for item in (provenance, grounding, concentration, consent):
        if item is not None and item.frame_set_digest != frames.frame_set_digest:
            raise PermissionError("third-wave forensic receipt is foreign or stale")
    if provenance:
        for finding in provenance.findings:
            for flag in finding.flags:
                add("high" if flag in ("partial_retained_text",
                    "preserved_text_hash_requires_review") else "medium",
                    "capture_provenance:" + flag, (finding.source_id,))
    if grounding:
        for item in grounding.objectives:
            if item.missing_evidence_review:
                add("high", "operator_objective_lexical_deficit", (), (item.objective_id,))
            if item.prohibited_term_passages:
                add("high", "operator_blocked_term_observed", (), (item.objective_id,))
    if concentration:
        for item in concentration.source_profiles:
            if item.repeated_cross_objective_anchors:
                add("medium", "citation_reuse_across_objectives", (item.source_id,), item.objective_ids)
        if concentration.repeated_text_hashes_across_sources:
            add("medium", "identical_selected_passage_content_cross_source",
                concentration.held_source_ids)
    if consent and consent.warning == "renewal_review_due":
        add("high", "mandate_consent_expiry_near")
    for item in (usage, gaps, context_budget):
        if item is not None and item.frame_set_digest != frames.frame_set_digest:
            raise PermissionError("fourth-wave source review receipt is foreign")
    if usage:
        for source_id in usage.cross_objective_reuse_sources:
            add("medium", "source_reused_across_objectives", (source_id,))
    if gaps:
        for row in gaps.gaps:
            for code in row.review_deficit_codes:
                add("high" if row.urgency_tier == "urgent_human_research"
                    else "medium", "research_gap:" + code, (), (row.objective_id,))
    if context_budget:
        if context_budget.over_campaign_evidence_char_limit:
            add("high", "untrusted_evidence_character_budget_exceeded")
        if context_budget.over_explicit_context_byte_limit:
            add("high", "untrusted_context_byte_budget_exceeded")
        if context_budget.source_concentration_review:
            add("medium", "context_dominated_by_single_source",
                (context_budget.hottest_source_id,) if context_budget.hottest_source_id else ())
    for item in (extraction, query_support, origins, selection_fairness,
                 risk_ablation, script_coverage):
        if item is not None and item.frame_set_digest != frames.frame_set_digest:
            raise PermissionError("fifth-wave source review receipt is foreign")
    if extraction:
        for finding in extraction.findings:
            for code in finding.review_codes:
                add("high" if code in ("nonprintable_extraction_characters",
                                      "repeated_character_payload") else "medium",
                    "extraction_quality:" + code, (finding.source_id,))
    if query_support:
        for finding in query_support.findings:
            if finding.no_selected_evidence:
                add("high", "query_support:no_selected_evidence", (),
                    (finding.objective_id,))
            elif finding.only_one_query_variant:
                add("medium", "query_support:single_variant", (),
                    (finding.objective_id,))
    if origins:
        for finding in origins.findings:
            for code in finding.flags:
                add("high" if code in ("possible_sensitive_query_parameter_name",
                                       "observed_origin_host_handoff") else "medium",
                    "source_origin:" + code, (finding.source_id,))
    if selection_fairness:
        for finding in selection_fairness.findings:
            if finding.source_dominance_review:
                add("medium", "selection:source_character_dominance", (),
                    (finding.objective_id,))
            if finding.host_dominance_review:
                add("medium", "selection:host_character_dominance", (),
                    (finding.objective_id,))
    if risk_ablation:
        for finding in risk_ablation.findings:
            if finding.no_usable_selected_evidence_in_scenario:
                add("high", "risk_ablation:no_selected_evidence", (),
                    (finding.objective_id,))
            elif finding.hypothetical_passage_shortfall:
                add("medium", "risk_ablation:insufficient_passages", (),
                    (finding.objective_id,))
    if script_coverage:
        for finding in script_coverage.findings:
            if finding.lexical_coverage_review:
                add("medium", "script_coverage:operator_term_bias", (),
                    (finding.objective_id,))
    ordering = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    ranked = sorted(signals, key=lambda row: (ordering[row[0]], row[1], row[2], row[3]))
    if len(ranked) > max_tasks:
        raise ValueError("forensic review overflow cannot silently discard holds")
    tasks = []
    for risk, reason, sources, goals in ranked:
        payload = {
            "risk": risk, "reason": reason, "sources": sources, "goals": goals,
            "snapshot": frames.snapshot_digest, "policy": frames.policy_digest,
        }
        signature = digest(payload)
        tasks.append(ForensicReviewTask(
            signature[:24], risk, reason, sources, goals,
            frames.snapshot_digest, frames.policy_digest, signature,
        ))
    held_sources = tuple(sorted({x for task in tasks for x in task.source_ids}))
    held_objectives = tuple(sorted({x for task in tasks for x in task.objective_ids}))
    return ForensicReviewQueue(
        frames.frame_set_digest, tuple(tasks),
        sum(x.risk == "critical" for x in tasks),
        held_sources, held_objectives,
        digest({"frames": frames.frame_set_digest,
                "tasks": [asdict(x) for x in tasks], "limit": max_tasks}),
    )

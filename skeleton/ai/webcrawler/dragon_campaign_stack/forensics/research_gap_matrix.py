"""Objective-level research deficit synthesis without generating new URLs.

Combines lexical grounding, selected-source resilience, provenance uncertainty
and host evidence concentration. The output is advisory review work only,
never an automated crawl dispatch, conclusion or operator consent extension.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from ..contracts import digest
from ..objectives import ObjectivePlan
from .frames import FrameSet
from .objective_grounding import ObjectiveGroundingReport
from .objective_resilience import ObjectiveResilience
from .host_exposure import HostExposureReport
from .provenance_posture import ProvenancePosture
from .source_usage_map import SourceUsageMap


@dataclass(frozen=True)
class ResearchGap:
    objective_id: str
    importance: float
    selected_sources: int
    observed_host_count: int
    lexical_passage_shortfall: int
    independence_scenario_shortfall: int
    review_deficit_codes: tuple[str, ...]
    urgency_tier: str
    evidence_ready_for_publication: bool = False
    autonomous_discovery_authorized: bool = False


@dataclass(frozen=True)
class ResearchGapMatrix:
    frame_set_digest: str
    plan_digest: str
    grounding_digest: str
    resilience_digest: str
    source_usage_digest: str
    gaps: tuple[ResearchGap, ...]
    urgent_objectives: tuple[str, ...]
    review_required_objectives: tuple[str, ...]
    matrix_digest: str
    mission_complete: bool = False
    reviewed_knowledge_created: bool = False
    speculative_url_discovery_performed: bool = False


def synthesize_research_gaps(
    frames: FrameSet, plan: ObjectivePlan,
    grounding: ObjectiveGroundingReport,
    resilience: ObjectiveResilience,
    exposure: HostExposureReport,
    provenance: ProvenancePosture,
    usage: SourceUsageMap,
) -> ResearchGapMatrix:
    if not all(isinstance(item, cls) for item, cls in (
        (frames, FrameSet), (plan, ObjectivePlan),
        (grounding, ObjectiveGroundingReport), (resilience, ObjectiveResilience),
        (exposure, HostExposureReport), (provenance, ProvenancePosture),
        (usage, SourceUsageMap),
    )):
        raise TypeError("current typed source-only research receipts required")
    if any(x != frames.frame_set_digest for x in (
        grounding.frame_set_digest, resilience.frame_set_digest,
        exposure.frame_set_digest, provenance.frame_set_digest,
        usage.frame_set_digest,
    )):
        raise PermissionError("research deficit inputs span different selected captures")
    if any(x != plan.plan_digest for x in (
        grounding.objective_plan_digest, resilience.objective_plan_digest,
        exposure.plan_digest, usage.objective_plan_digest,
    )) or plan.mandate_digest != frames.mandate_digest:
        raise PermissionError("research deficit receipts span different operator plans")
    by_grounding = {row.objective_id: row for row in grounding.objectives}
    by_resilience = {row.objective_id: row for row in resilience.objectives}
    by_host = {row.objective_id: row for row in exposure.by_objective}
    universe = {o.objective_id for o in plan.objectives}
    if any(set(rows) != universe for rows in (
        by_grounding, by_resilience, by_host,
    )):
        raise PermissionError("objective coverage of audit universe incomplete")
    held_by_source = set(provenance.held_source_ids)
    source_to_goals = {row.source_id: set(row.objective_ids) for row in usage.source_uses}
    rows = []
    urgent = []
    held = []
    for objective in plan.objectives:
        oid = objective.objective_id
        g, r, h = by_grounding[oid], by_resilience[oid], by_host[oid]
        flags = set()
        if not r.selected_sources:
            flags.add("no_selected_source")
        if g.lexical_passage_shortfall:
            flags.add("insufficient_exact_operator_terms")
        if g.prohibited_term_passages:
            flags.add("operator_blocked_terms")
        if r.hypothetical_family_shortfall:
            flags.add("potentially_correlated_sources")
        if r.surviving_sources_after_worst_host_loss == 0 and r.selected_sources:
            flags.add("host_failure_eliminates_evidence")
        if h.single_host_review:
            flags.add("host_concentration")
        if any(oid in source_to_goals.get(source_id, set())
               for source_id in held_by_source):
            flags.add("source_provenance_limitations")
        # Every selected passage remains unreviewed external content; even an
        # empty deficit set can never certify a factual answer.
        if flags:
            held.append(oid)
        tier = (
            "urgent_human_research" if "no_selected_source" in flags
                or "operator_blocked_terms" in flags
            else "review_first" if flags else "human_fact_check_pending"
        )
        if tier == "urgent_human_research":
            urgent.append(oid)
        rows.append(ResearchGap(
            oid, objective.priority, r.selected_sources, h.distinct_hosts,
            g.lexical_passage_shortfall, r.hypothetical_family_shortfall,
            tuple(sorted(flags)), tier,
        ))
    rows.sort(key=lambda r: (
        {"urgent_human_research": 0, "review_first": 1, "human_fact_check_pending": 2}[r.urgency_tier],
        -r.importance, r.objective_id,
    ))
    payload = {
        "frames": frames.frame_set_digest, "plan": plan.plan_digest,
        "grounding": grounding.report_digest,
        "resilience": resilience.report_digest,
        "exposure": exposure.report_digest,
        "provenance": provenance.posture_digest,
        "usage": usage.map_digest,
        "gaps": [asdict(x) for x in rows],
    }
    return ResearchGapMatrix(
        frames.frame_set_digest, plan.plan_digest,
        grounding.report_digest, resilience.report_digest, usage.map_digest,
        tuple(rows), tuple(sorted(urgent)), tuple(sorted(held)), digest(payload),
    )

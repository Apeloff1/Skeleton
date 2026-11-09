"""Counterfactual research survivability after conservative source-risk holds.

A finding never automatically deletes or revokes a source. For *review
planning only*, this stage removes selected sources carrying injection,
privacy, active-content, extraction or origin anomalies and recalculates
objective-level surviving evidence and minimum selected passage targets.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass

from ..contracts import digest
from ..objectives import ObjectivePlan
from .frames import FrameSet
from .text_security import TextSecurityReport
from .privacy_signals import PrivacySignalReport
from .active_content import ActiveContentReport
from .extraction_quality import ExtractionQualityReport
from .source_origin_audit import SourceOriginAudit


@dataclass(frozen=True)
class RiskAblationFinding:
    objective_id: str
    selected_passages_before: int
    selected_passages_after: int
    sources_before: int
    sources_after: int
    hosts_before: int
    hosts_after: int
    hypothetical_passage_shortfall: int
    no_usable_selected_evidence_in_scenario: bool
    requires_human_source_review: bool = True
    source_mutation_committed: bool = False


@dataclass(frozen=True)
class RiskAblationReport:
    frame_set_digest: str
    objective_plan_digest: str
    held_source_ids: tuple[str, ...]
    held_by_security: tuple[str, ...]
    held_by_privacy: tuple[str, ...]
    held_by_active_content: tuple[str, ...]
    held_by_extraction: tuple[str, ...]
    held_by_origin: tuple[str, ...]
    findings: tuple[RiskAblationFinding, ...]
    total_passages_lost_in_scenario: int
    objectives_emptied_in_scenario: tuple[str, ...]
    report_digest: str
    automatic_source_withdrawal: bool = False
    additional_crawling_authorized: bool = False
    report_is_verified_fact: bool = False


def simulate_risk_ablations(
    frames: FrameSet, plan: ObjectivePlan,
    security: TextSecurityReport, privacy: PrivacySignalReport,
    active: ActiveContentReport, extraction: ExtractionQualityReport,
    origins: SourceOriginAudit,
) -> RiskAblationReport:
    if not all(isinstance(x, cls) for x, cls in (
        (frames, FrameSet), (plan, ObjectivePlan),
        (security, TextSecurityReport), (privacy, PrivacySignalReport),
        (active, ActiveContentReport), (extraction, ExtractionQualityReport),
        (origins, SourceOriginAudit),
    )):
        raise TypeError("typed protected source-risk inputs required")
    if (frames.mandate_digest != plan.mandate_digest
            or origins.mandate_digest != frames.mandate_digest
            or origins.source_snapshot_digest != frames.snapshot_digest
            or any(x.frame_set_digest != frames.frame_set_digest for x in (
                security, privacy, active, extraction, origins
            ))):
        raise PermissionError("ablation input references foreign selected evidence")
    all_sources = {f.anchor.source_id for f in frames.frames}
    sources = (
        set(security.held_sources),
        set(privacy.held_source_ids),
        set(active.held_source_ids),
        set(extraction.held_source_ids),
        set(origins.review_source_ids),
    )
    if not all(held <= all_sources for held in sources):
        raise PermissionError("source risk annotation not in selected source universe")
    held = set().union(*sources)
    universe = {goal.objective_id for goal in plan.objectives}
    before = defaultdict(list)
    after = defaultdict(list)
    for frame in frames.frames:
        anchor = frame.anchor
        if not set(anchor.objective_ids) <= universe:
            raise PermissionError("risk ablation contains unmandated objective")
        for goal in anchor.objective_ids:
            before[goal].append(anchor)
            if anchor.source_id not in held:
                after[goal].append(anchor)
    findings, empty = [], []
    for goal in plan.objectives:
        old, new = before[goal.objective_id], after[goal.objective_id]
        gap = max(0, goal.minimum_reviewable_passages - len(new))
        if not new:
            empty.append(goal.objective_id)
        findings.append(RiskAblationFinding(
            goal.objective_id, len(old), len(new),
            len({x.source_id for x in old}),
            len({x.source_id for x in new}),
            len({x.host for x in old}), len({x.host for x in new}),
            gap, not bool(new),
        ))
    payload = {
        "frames": frames.frame_set_digest,
        "plan": plan.plan_digest,
        "security": security.report_digest, "privacy": privacy.report_digest,
        "active": active.report_digest,
        "extraction": extraction.report_digest,
        "origin": origins.audit_digest,
        "held": sorted(held),
        "findings": [asdict(x) for x in findings],
    }
    return RiskAblationReport(
        frames.frame_set_digest, plan.plan_digest, tuple(sorted(held)),
        tuple(sorted(sources[0])), tuple(sorted(sources[1])),
        tuple(sorted(sources[2])), tuple(sorted(sources[3])),
        tuple(sorted(sources[4])), tuple(findings),
        sum(x.selected_passages_before - x.selected_passages_after for x in findings),
        tuple(empty), digest(payload),
    )

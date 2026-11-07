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
    *, max_tasks: int = 256,
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

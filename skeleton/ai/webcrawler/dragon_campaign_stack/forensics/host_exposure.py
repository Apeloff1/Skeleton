"""Bounded source and host selection concentration diagnostics.

Effective-host count is the inverse Simpson concentration index; it is not an
independence count, a fact accuracy estimate or a source-publishing grant.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass

from ..contracts import digest
from ..objectives import ObjectivePlan
from .frames import FrameSet


@dataclass(frozen=True)
class HostExposure:
    objective_id: str
    selected_passages: int
    distinct_sources: int
    distinct_hosts: int
    busiest_host: str | None
    busiest_host_passage_share: float
    passage_hhi: float
    effective_host_count: float
    single_host_review: bool
    host_independence_verified: bool = False


@dataclass(frozen=True)
class HostExposureReport:
    frame_set_digest: str
    plan_digest: str
    by_objective: tuple[HostExposure, ...]
    concentration_review_objectives: tuple[str, ...]
    report_digest: str
    objective_coverage_certified: bool = False
    independent_sources_verified: bool = False


def measure_host_exposure(frames: FrameSet, plan: ObjectivePlan) -> HostExposureReport:
    if not isinstance(frames, FrameSet) or not isinstance(plan, ObjectivePlan):
        raise TypeError("typed selection and operator objectives required")
    if frames.mandate_digest != plan.mandate_digest:
        raise PermissionError("cross-mandate host exposure")
    goals = {x.objective_id for x in plan.objectives}
    grouped = defaultdict(list)
    for frame in frames.frames:
        for objective in frame.anchor.objective_ids:
            if objective not in goals:
                raise PermissionError("unmandated objective in host exposure")
            grouped[objective].append(frame.anchor)
    outputs = []
    holds = []
    for item in plan.objectives:
        anchors = grouped[item.objective_id]
        counts = Counter(x.host for x in anchors)
        n = len(anchors)
        busiest = sorted(counts.items(), key=lambda x: (-x[1], x[0]))
        share = busiest[0][1] / n if busiest else 0.
        hhi = sum((count / n) ** 2 for count in counts.values()) if n else 0.
        single = len(counts) <= 1
        if single or hhi >= .75:
            holds.append(item.objective_id)
        outputs.append(HostExposure(
            item.objective_id, n, len({x.source_id for x in anchors}), len(counts),
            busiest[0][0] if busiest else None,
            round(share, 6), round(hhi, 6),
            round(1 / hhi, 6) if hhi else 0., single,
        ))
    payload = {
        "frames": frames.frame_set_digest, "plan": plan.plan_digest,
        "objectives": [asdict(x) for x in outputs],
    }
    return HostExposureReport(
        frames.frame_set_digest, plan.plan_digest, tuple(outputs),
        tuple(holds), digest(payload),
    )

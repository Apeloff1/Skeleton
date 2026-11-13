"""Crawl capture-age posture for each operator objective, not remote truth age.

Uses only canonical capture timestamps under exact snapshot policy. The date
may describe a recently fetched copy of old or inaccurate material; no field
asserts that the external origin remains current.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite
from collections import defaultdict

from ...operations import CrawlRun
from ..contracts import CampaignMandate, digest, ensure_snapshot_scope
from ..objectives import ObjectivePlan
from .frames import FrameSet


@dataclass(frozen=True)
class CaptureAgeFinding:
    objective_id: str
    selected_source_count: int
    stale_capture_ids: tuple[str, ...]
    unknown_capture_ids: tuple[str, ...]
    youngest_capture_seconds: float | None
    oldest_capture_seconds: float | None
    meets_capture_age_target: bool
    remote_content_freshness_verified: bool = False


@dataclass(frozen=True)
class CaptureAgeReport:
    frame_set_digest: str
    objective_plan_digest: str
    findings: tuple[CaptureAgeFinding, ...]
    held_source_ids: tuple[str, ...]
    report_digest: str
    live_origin_rechecked: bool = False
    recrawl_authorized: bool = False


def inspect_capture_age(
    mandate: CampaignMandate, snapshot: dict[str, object],
    frames: FrameSet, plan: ObjectivePlan,
    *, now: float, authorized: bool,
) -> CaptureAgeReport:
    mandate.admit(now=now, authorized=authorized)
    ensure_snapshot_scope(snapshot, mandate)
    if not isinstance(frames, FrameSet) or not isinstance(plan, ObjectivePlan):
        raise TypeError("typed provenance-bound frames and objectives required")
    canonical = CrawlRun.from_snapshot(snapshot).snapshot()
    if (frames.mandate_digest != mandate.fingerprint
            or frames.snapshot_digest != canonical["snapshot_digest"]
            or plan.mandate_digest != mandate.fingerprint):
        raise PermissionError("foreign capture age source")
    ages: dict[str, float | None] = {}
    grouped = defaultdict(set)
    universe = {x.objective_id for x in plan.objectives}
    for frame in frames.frames:
        source_id = frame.anchor.source_id
        if source_id not in ages:
            source = canonical["sources"][source_id]
            timestamp = source.get("fetched_at")
            if (type(timestamp) not in (float, int)
                    or not isfinite(timestamp) or timestamp < 0
                    or timestamp > now):
                ages[source_id] = None
            else:
                ages[source_id] = max(0., float(now - timestamp))
        for goal in frame.anchor.objective_ids:
            if goal not in universe:
                raise PermissionError("unknown objective in capture age source")
            grouped[goal].add(source_id)
    findings = []
    held = set()
    for objective in plan.objectives:
        ids = grouped[objective.objective_id]
        unknown = tuple(sorted(x for x in ids if ages[x] is None))
        stale = tuple(sorted(
            x for x in ids
            if ages[x] is not None and ages[x] > objective.max_source_age_seconds
        ))
        held.update(unknown)
        held.update(stale)
        values = sorted(ages[x] for x in ids if ages[x] is not None)
        findings.append(CaptureAgeFinding(
            objective.objective_id, len(ids), stale, unknown,
            values[0] if values else None, values[-1] if values else None,
            bool(ids) and not stale and not unknown,
        ))
    payload = {
        "frames": frames.frame_set_digest, "plan": plan.plan_digest,
        "now": now, "findings": [asdict(f) for f in findings],
    }
    return CaptureAgeReport(
        frames.frame_set_digest, plan.plan_digest, tuple(findings),
        tuple(sorted(held)), digest(payload),
    )

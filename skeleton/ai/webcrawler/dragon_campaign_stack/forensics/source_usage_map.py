"""Bounded reverse source-to-objective audit map for a protected research run.

This is a metadata-only index of selected exact citation anchors, not a new
corpus, index, content cache, knowledge store or independently granted right.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass

from ..contracts import digest
from ..objectives import ObjectivePlan
from .frames import FrameSet


@dataclass(frozen=True)
class SourceObjectiveUse:
    source_id: str
    host: str
    content_hash: str
    objective_ids: tuple[str, ...]
    passage_anchor_digests: tuple[str, ...]
    selected_passage_count: int
    selected_chars: int
    used_in_multiple_objectives: bool
    approved_knowledge: bool = False


@dataclass(frozen=True)
class SourceUsageMap:
    frame_set_digest: str
    objective_plan_digest: str
    selected_source_count: int
    selected_anchor_count: int
    source_uses: tuple[SourceObjectiveUse, ...]
    unrepresented_objectives: tuple[str, ...]
    cross_objective_reuse_sources: tuple[str, ...]
    map_digest: str
    sources_independent: bool = False
    factual_evidence_certified: bool = False
    source_text_exported: bool = False


def compile_source_usage_map(frames: FrameSet, plan: ObjectivePlan) -> SourceUsageMap:
    if not isinstance(frames, FrameSet) or not isinstance(plan, ObjectivePlan):
        raise TypeError("exact current source frames and operator plan required")
    if frames.mandate_digest != plan.mandate_digest:
        raise PermissionError("foreign source usage plan")
    expected = {item.objective_id for item in plan.objectives}
    if len(expected) != len(plan.objectives) or not expected or len(expected) > 32:
        raise ValueError("bounded unique operator objective plan required")
    source_rows = defaultdict(list)
    covered = set()
    for frame in frames.frames:
        anchor = frame.anchor
        if not set(anchor.objective_ids) <= expected:
            raise PermissionError("source usage references foreign objective")
        if not anchor.objective_ids:
            raise PermissionError("selected source has no operator objective")
        source_rows[anchor.source_id].append(anchor)
        covered.update(anchor.objective_ids)
    if len(source_rows) > 32 or len(frames.frames) > 64:
        raise ValueError("source usage capacity exceeded")
    uses, multi = [], []
    for source_id, anchors in sorted(source_rows.items()):
        hosts = {a.host for a in anchors}
        hashes = {a.source_hash for a in anchors}
        if len(hosts) != 1 or len(hashes) != 1:
            raise PermissionError("one source identity maps to conflicting content or origin")
        goals = tuple(sorted({goal for a in anchors for goal in a.objective_ids}))
        anchors_by_id = tuple(sorted(a.anchor_digest for a in anchors))
        if len(set(anchors_by_id)) != len(anchors_by_id):
            raise ValueError("repeated source selection anchor identity")
        if len(goals) > 1:
            multi.append(source_id)
        uses.append(SourceObjectiveUse(
            source_id, next(iter(hosts)), next(iter(hashes)), goals,
            anchors_by_id, len(anchors), sum(a.chars for a in anchors),
            len(goals) > 1,
        ))
    payload = {
        "frames": frames.frame_set_digest, "plan": plan.plan_digest,
        "uses": [asdict(row) for row in uses],
        "unrepresented": sorted(expected - covered),
    }
    return SourceUsageMap(
        frames.frame_set_digest, plan.plan_digest, len(uses),
        len(frames.frames), tuple(uses),
        tuple(sorted(expected - covered)), tuple(multi), digest(payload),
    )

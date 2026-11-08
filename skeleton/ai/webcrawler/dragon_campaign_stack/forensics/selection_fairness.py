"""Objective-weighted selected-evidence distribution and concentration.

A source may be selected repeatedly by a lexical ranker. Passage share,
selected-byte share, effective source counts and host share are only audit
signals; they do not establish factual independence or relevance.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from math import log2

from ..contracts import digest
from ..objectives import ObjectivePlan
from .frames import FrameSet


@dataclass(frozen=True)
class SelectionFairnessFinding:
    objective_id: str
    selected_passages: int
    selected_sources: int
    selected_hosts: int
    selected_characters: int
    largest_source_character_share: float
    largest_host_character_share: float
    effective_sources_by_characters: float
    normalized_source_entropy: float
    source_dominance_review: bool
    host_dominance_review: bool
    independent_evidence_confirmed: bool = False


@dataclass(frozen=True)
class SelectionFairnessAudit:
    frame_set_digest: str
    objective_plan_digest: str
    findings: tuple[SelectionFairnessFinding, ...]
    source_dominance_objectives: tuple[str, ...]
    host_dominance_objectives: tuple[str, ...]
    no_selected_evidence_objectives: tuple[str, ...]
    audit_digest: str
    retrieval_reranked: bool = False
    factual_relevance_confirmed: bool = False


def measure_selection_fairness(
    frames: FrameSet, plan: ObjectivePlan, *,
    source_dominance_threshold: float = .80,
    host_dominance_threshold: float = .85,
) -> SelectionFairnessAudit:
    if not isinstance(frames, FrameSet) or not isinstance(plan, ObjectivePlan):
        raise TypeError("typed selected frames and operator objectives required")
    if frames.mandate_digest != plan.mandate_digest:
        raise PermissionError("selection fairness crosses campaign mandate")
    for value in (source_dominance_threshold, host_dominance_threshold):
        if type(value) not in (int, float) or not .5 <= value <= 1.:
            raise ValueError("invalid dominance review threshold")
    universe = {o.objective_id for o in plan.objectives}
    groups = defaultdict(list)
    for frame in frames.frames:
        if not set(frame.anchor.objective_ids) <= universe:
            raise PermissionError("forensic selection contains foreign objective")
        for goal in frame.anchor.objective_ids:
            groups[goal].append(frame.anchor)
    findings, source_holds, host_holds, empty = [], [], [], []
    for objective in plan.objectives:
        selected = groups[objective.objective_id]
        sources, hosts = defaultdict(int), defaultdict(int)
        for a in selected:
            sources[a.source_id] += a.chars
            hosts[a.host] += a.chars
        total = sum(sources.values())
        shares = [n / total for n in sources.values()] if total else []
        host_shares = [n / total for n in hosts.values()] if total else []
        hhi = sum(s * s for s in shares)
        entropy = -sum(s * log2(s) for s in shares) if shares else 0.0
        entropy_limit = log2(len(shares)) if len(shares) > 1 else 0.0
        largest_source = max(shares, default=0.0)
        largest_host = max(host_shares, default=0.0)
        source_hold = largest_source >= source_dominance_threshold and bool(selected)
        host_hold = largest_host >= host_dominance_threshold and bool(selected)
        if source_hold:
            source_holds.append(objective.objective_id)
        if host_hold:
            host_holds.append(objective.objective_id)
        if not selected:
            empty.append(objective.objective_id)
        findings.append(SelectionFairnessFinding(
            objective.objective_id, len(selected), len(sources), len(hosts),
            total, round(largest_source, 6), round(largest_host, 6),
            round(1.0 / hhi, 6) if hhi else 0.0,
            round(entropy / entropy_limit, 6) if entropy_limit else 0.0,
            source_hold, host_hold,
        ))
    payload = {
        "frames": frames.frame_set_digest, "plan": plan.plan_digest,
        "source_threshold": source_dominance_threshold,
        "host_threshold": host_dominance_threshold,
        "findings": [asdict(x) for x in findings],
    }
    return SelectionFairnessAudit(
        frames.frame_set_digest, plan.plan_digest, tuple(findings),
        tuple(source_holds), tuple(host_holds), tuple(empty), digest(payload),
    )

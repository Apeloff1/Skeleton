"""Objective-level leave-one-source, leave-one-host and copy-family sensitivity.

These are pessimistic selected-evidence scenarios. The family-collapse scenario
is not an estimate of true provenance. A lack of overlap is not certification
of independence, factual correctness, citation quality or publication rights.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass

from ..contracts import digest
from ..objectives import ObjectivePlan
from .frames import FrameSet
from .source_reuse import SourceReuseReport


@dataclass(frozen=True)
class ObjectiveSensitivity:
    objective_id: str
    requested_attested_groups: int
    selected_passages: int
    selected_sources: int
    observed_hosts: int
    distinct_content_sensitivity_groups: int
    possible_near_copy_groups: int
    surviving_sources_after_worst_source_loss: int
    surviving_sources_after_worst_host_loss: int
    surviving_possible_groups_after_host_loss: int
    hypothetical_family_shortfall: int
    worst_loss_host: str | None
    review_required: bool = True
    independent_witnesses_confirmed: bool = False


@dataclass(frozen=True)
class ObjectiveResilience:
    frame_set_digest: str
    objective_plan_digest: str
    source_reuse_digest: str
    objectives: tuple[ObjectiveSensitivity, ...]
    no_selection_objectives: tuple[str, ...]
    potential_source_single_points: tuple[str, ...]
    potential_host_single_points: tuple[str, ...]
    report_digest: str
    factual_conclusions_drawn: bool = False
    independent_sources_certified: bool = False


def analyze_objective_resilience(
    frames: FrameSet, plan: ObjectivePlan, reuse: SourceReuseReport,
) -> ObjectiveResilience:
    if (not isinstance(frames, FrameSet) or not isinstance(plan, ObjectivePlan)
            or not isinstance(reuse, SourceReuseReport)):
        raise TypeError("typed objective and exact selected-source receipts required")
    if plan.mandate_digest != frames.mandate_digest or (
        reuse.frame_set_digest != frames.frame_set_digest
    ):
        raise PermissionError("objective counterfactual uses foreign evidence")
    universe = {item.objective_id for item in plan.objectives}
    grouped: dict[str, set[str]] = defaultdict(set)
    host_by_source: dict[str, str] = {}
    hash_by_source: dict[str, str] = {}
    for frame in frames.frames:
        anchor = frame.anchor
        host_by_source[anchor.source_id] = anchor.host
        hash_by_source[anchor.source_id] = anchor.source_hash
        for objective in anchor.objective_ids:
            if objective not in universe:
                raise PermissionError("unmandated objective in retrieved passage")
            grouped[objective].add(anchor.source_id)
    parent = {source_id: source_id for source_id in host_by_source}
    def root(value: str) -> str:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value
    for comp in reuse.components:
        members = comp.source_ids
        if any(source_id not in parent for source_id in members):
            raise PermissionError("source reuse includes unselected source")
        for member in members[1:]:
            a, b = root(members[0]), root(member)
            if a != b:
                parent[max(a, b)] = min(a, b)
    rows: list[ObjectiveSensitivity] = []
    no_selection, source_singles, host_singles = [], [], []
    for objective in plan.objectives:
        ids = grouped[objective.objective_id]
        hosts = {host_by_source[source_id] for source_id in ids}
        exact_groups = len({hash_by_source[x] for x in ids})
        possible = len({root(x) for x in ids})
        host_scenarios = []
        for host in sorted(hosts):
            remaining = {x for x in ids if host_by_source[x] != host}
            host_scenarios.append((len({root(x) for x in remaining}), len(remaining), host))
        worst = min(host_scenarios) if host_scenarios else (0, 0, None)
        single_loss = max(0, len(ids) - 1)
        passage_count = sum(
            objective.objective_id in frame.anchor.objective_ids
            for frame in frames.frames
        )
        rows.append(ObjectiveSensitivity(
            objective.objective_id, objective.minimum_attested_groups,
            passage_count, len(ids), len(hosts), exact_groups, possible,
            single_loss, worst[1], worst[0],
            max(0, objective.minimum_attested_groups - possible),
            worst[2],
        ))
        if not ids:
            no_selection.append(objective.objective_id)
        if len(ids) <= 1:
            source_singles.append(objective.objective_id)
        if len(hosts) <= 1:
            host_singles.append(objective.objective_id)
    payload = {
        "frames": frames.frame_set_digest,
        "plan": plan.plan_digest, "reuse": reuse.report_digest,
        "objectives": [asdict(row) for row in rows],
    }
    return ObjectiveResilience(
        frames.frame_set_digest, plan.plan_digest, reuse.report_digest,
        tuple(rows), tuple(no_selection), tuple(source_singles),
        tuple(host_singles), digest(payload),
    )

"""Select bounded organization work for an always-on repository steward."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .growth import growth_recommendations
from .model import RepositoryModel
from .workgraph import WorkNode, build_work_graph


@dataclass(frozen=True, slots=True)
class StewardObjective:
    identity: str
    source: str
    lane: str
    zone: str
    priority: int
    objective: str
    conflict_keys: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "identity": self.identity,
            "source": self.source,
            "lane": self.lane,
            "zone": self.zone,
            "priority": self.priority,
            "objective": self.objective,
            "conflict_keys": list(self.conflict_keys),
        }


@dataclass(frozen=True, slots=True)
class StewardPlan:
    repository_fingerprint: str
    objectives: tuple[StewardObjective, ...]
    deferred: int

    def as_dict(self) -> dict[str, object]:
        return {
            "repository_fingerprint": self.repository_fingerprint,
            "objectives": [item.as_dict() for item in self.objectives],
            "deferred": self.deferred,
        }


def _from_work(node: WorkNode) -> StewardObjective:
    return StewardObjective(
        identity=node.identity,
        source="finding",
        lane=node.lane,
        zone=node.zone,
        priority=node.priority,
        objective=node.objective,
        conflict_keys=node.conflict_keys,
    )


def select_steward_plan(
    model: RepositoryModel,
    *,
    active_conflicts: Iterable[str] = (),
    max_objectives: int = 3,
) -> StewardPlan:
    if isinstance(max_objectives, bool) or not isinstance(max_objectives, int) or not 1 <= max_objectives <= 16:
        raise ValueError("max_objectives must be in [1,16]")
    conflicts = set(active_conflicts)
    graph = build_work_graph(model)
    selected: list[StewardObjective] = []

    for node in graph.ready(active_conflicts=conflicts, limit=max_objectives):
        objective = _from_work(node)
        selected.append(objective)
        conflicts.update(objective.conflict_keys)
        if len(selected) >= max_objectives:
            break

    if len(selected) < max_objectives:
        for recommendation in growth_recommendations(model, limit=32):
            keys = {f"zone:{recommendation.zone}", "lane:architecture"}
            if conflicts.intersection(keys):
                continue
            identity = f"growth:{recommendation.code}:{recommendation.zone}"
            selected.append(StewardObjective(
                identity=identity,
                source="growth",
                lane="architecture",
                zone=recommendation.zone,
                priority=recommendation.priority,
                objective=recommendation.objective,
                conflict_keys=tuple(sorted(keys)),
            ))
            conflicts.update(keys)
            if len(selected) >= max_objectives:
                break

    total = len(graph.nodes) + len(growth_recommendations(model, limit=32))
    return StewardPlan(
        repository_fingerprint=model.fingerprint,
        objectives=tuple(selected),
        deferred=max(0, total - len(selected)),
    )

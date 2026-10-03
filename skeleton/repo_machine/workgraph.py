"""Conflict-aware work graph derived from repository organization evidence."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .model import RepositoryModel
from .planner import WorkCandidate, derive_work_candidates


@dataclass(frozen=True, slots=True)
class WorkNode:
    identity: str
    lane: str
    zone: str
    priority: int
    objective: str
    conflict_keys: tuple[str, ...]
    prerequisites: tuple[str, ...]
    evidence: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "identity": self.identity,
            "lane": self.lane,
            "zone": self.zone,
            "priority": self.priority,
            "objective": self.objective,
            "conflict_keys": list(self.conflict_keys),
            "prerequisites": list(self.prerequisites),
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True, slots=True)
class WorkGraph:
    nodes: tuple[WorkNode, ...]
    _ordered_nodes: tuple[WorkNode, ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "_ordered_nodes",
            tuple(sorted(self.nodes, key=lambda item: (-item.priority, item.identity))),
        )

    def as_dict(self) -> dict[str, object]:
        return {"nodes": [node.as_dict() for node in self.nodes]}

    def ready(
        self,
        completed: Iterable[str] = (),
        active_conflicts: Iterable[str] = (),
        *,
        limit: int = 8,
    ) -> tuple[WorkNode, ...]:
        done = set(completed)
        conflicts = set(active_conflicts)
        ready: list[WorkNode] = []
        for node in self._ordered_nodes:
            if any(prerequisite not in done for prerequisite in node.prerequisites):
                continue
            if any(key in conflicts for key in node.conflict_keys):
                continue
            ready.append(node)
            conflicts.update(node.conflict_keys)
            if len(ready) >= limit:
                break
        return tuple(ready)


def _conflicts(
    candidate: WorkCandidate,
    dependents_by_zone: dict[str, tuple[str, ...]] | None = None,
) -> tuple[str, ...]:
    keys = {f"zone:{candidate.zone}", f"lane:{candidate.lane}"}
    if dependents_by_zone:
        keys.update(f"dependent-zone:{zone}" for zone in dependents_by_zone.get(candidate.zone, ()))
    if candidate.path:
        keys.add(f"path:{candidate.path}")
    return tuple(sorted(keys))


def build_work_graph(model: RepositoryModel, *, limit: int = 128) -> WorkGraph:
    candidates = derive_work_candidates(model, limit=limit)
    # Precompute the highest-priority prerequisite per zone once. The old
    # implementation sorted and scanned every candidate's zone repeatedly,
    # turning large work graphs into avoidable O(n²) planning work.
    best_prerequisite: dict[str, WorkCandidate] = {}
    for candidate in candidates:
        if candidate.lane not in {"repository-health", "architecture"}:
            continue
        current = best_prerequisite.get(candidate.zone)
        if current is None or (-candidate.priority, candidate.identity) < (
            -current.priority, current.identity
        ):
            best_prerequisite[candidate.zone] = candidate

    reverse_dependencies: dict[str, set[str]] = {}
    for subsystem in model.subsystems:
        for dependency in subsystem.dependencies:
            reverse_dependencies.setdefault(dependency, set()).add(subsystem.name)
    dependents_by_zone = {
        zone: tuple(sorted(values))
        for zone, values in reverse_dependencies.items()
    }

    nodes: list[WorkNode] = []
    for candidate in candidates:
        prerequisites: list[str] = []
        higher = best_prerequisite.get(candidate.zone)
        if (
            candidate.lane not in {"repository-health", "architecture"}
            and higher is not None
            and higher.priority > candidate.priority
        ):
            prerequisites.append(higher.identity)
        nodes.append(WorkNode(
            identity=candidate.identity,
            lane=candidate.lane,
            zone=candidate.zone,
            priority=candidate.priority,
            objective=candidate.objective,
            conflict_keys=_conflicts(candidate, dependents_by_zone),
            prerequisites=tuple(sorted(set(prerequisites))),
            evidence=candidate.evidence,
        ))
    return WorkGraph(tuple(nodes))

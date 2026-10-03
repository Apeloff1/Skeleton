"""Conflict-aware work graph with explicit dependency and readiness gates."""
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
    verification_paths: tuple[str, ...] = ()
    readiness: str = "ready"

    def as_dict(self) -> dict[str, object]:
        return {"identity": self.identity, "lane": self.lane, "zone": self.zone, "priority": self.priority,
                "objective": self.objective, "conflict_keys": list(self.conflict_keys),
                "prerequisites": list(self.prerequisites), "evidence": list(self.evidence),
                "verification_paths": list(self.verification_paths), "readiness": self.readiness}


@dataclass(frozen=True, slots=True)
class WorkGraph:
    nodes: tuple[WorkNode, ...]
    _ordered_nodes: tuple[WorkNode, ...] = field(init=False, repr=False, compare=False)
    _by_identity: dict[str, WorkNode] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        ordered = tuple(sorted(self.nodes, key=lambda item: (-item.priority, item.identity)))
        identities = {item.identity for item in ordered}
        if len(identities) != len(ordered):
            raise ValueError("work graph contains duplicate identities")
        by_identity = {item.identity: item for item in ordered}
        for node in ordered:
            missing = [item for item in node.prerequisites if item not in by_identity]
            if missing:
                raise ValueError(f"work graph has unknown prerequisites for {node.identity}")
        # Reject cycles so readiness can never deadlock on an invalid graph.
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(identity: str) -> None:
            if identity in visiting:
                raise ValueError(f"work graph contains prerequisite cycle at {identity}")
            if identity in visited:
                return
            visiting.add(identity)
            for prerequisite in by_identity[identity].prerequisites:
                visit(prerequisite)
            visiting.remove(identity)
            visited.add(identity)

        for identity in by_identity:
            visit(identity)
        object.__setattr__(self, "_ordered_nodes", ordered)
        object.__setattr__(self, "_by_identity", by_identity)

    def as_dict(self) -> dict[str, object]:
        return {"nodes": [node.as_dict() for node in self.nodes]}

    def ready(self, completed: Iterable[str] = (), active_conflicts: Iterable[str] = (), *, limit: int = 8) -> tuple[WorkNode, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer")
        done = set(completed)
        unknown = done - set(self._by_identity)
        if unknown:
            raise ValueError("completed contains unknown work identities")
        conflicts = set(active_conflicts)
        ready: list[WorkNode] = []
        for node in self._ordered_nodes:
            if node.identity in done or any(prerequisite not in done for prerequisite in node.prerequisites):
                continue
            if any(key in conflicts for key in node.conflict_keys):
                continue
            ready.append(node)
            conflicts.update(node.conflict_keys)
            if len(ready) >= limit:
                break
        return tuple(ready)

    def blocked(self, completed: Iterable[str] = ()) -> tuple[WorkNode, ...]:
        done = set(completed)
        return tuple(node for node in self._ordered_nodes
                     if node.identity not in done and any(prerequisite not in done for prerequisite in node.prerequisites))


def _conflicts(candidate: WorkCandidate, dependents_by_zone: dict[str, tuple[str, ...]] | None = None) -> tuple[str, ...]:
    keys = {f"zone:{candidate.zone}", f"lane:{candidate.lane}"}
    if dependents_by_zone:
        keys.update(f"dependent-zone:{zone}" for zone in dependents_by_zone.get(candidate.zone, ()))
    keys.update(f"dependency-zone:{zone}" for zone in candidate.dependency_zones)
    if candidate.path:
        keys.add(f"path:{candidate.path}")
    return tuple(sorted(keys))


def build_work_graph(model: RepositoryModel, *, limit: int = 128) -> WorkGraph:
    candidates = derive_work_candidates(model, limit=limit)
    best_prerequisite: dict[str, WorkCandidate] = {}
    for candidate in candidates:
        if candidate.lane not in {"repository-health", "architecture"}:
            continue
        current = best_prerequisite.get(candidate.zone)
        if current is None or (-candidate.priority, candidate.identity) < (-current.priority, current.identity):
            best_prerequisite[candidate.zone] = candidate
    reverse_dependencies: dict[str, set[str]] = {}
    for subsystem in model.subsystems:
        for dependency in subsystem.dependencies:
            reverse_dependencies.setdefault(dependency, set()).add(subsystem.name)
    dependents_by_zone = {zone: tuple(sorted(values)) for zone, values in reverse_dependencies.items()}
    nodes: list[WorkNode] = []
    for candidate in candidates:
        prerequisites = set(candidate.prerequisite_ids)
        higher = best_prerequisite.get(candidate.zone)
        if candidate.lane not in {"repository-health", "architecture"} and higher is not None and higher.priority > candidate.priority:
            prerequisites.add(higher.identity)
        nodes.append(WorkNode(
            identity=candidate.identity, lane=candidate.lane, zone=candidate.zone, priority=candidate.priority,
            objective=candidate.objective, conflict_keys=_conflicts(candidate, dependents_by_zone),
            prerequisites=tuple(sorted(prerequisites)), evidence=candidate.evidence,
            verification_paths=candidate.verification_paths, readiness="ready" if not prerequisites else "gated",
        ))
    return WorkGraph(tuple(nodes))

"""Conflict-aware work graph with explicit dependency, frontier, and critical-path intelligence."""
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
    decision_score: int = 0
    topology_confidence: int = 0
    blast_radius: int = 0
    critical_path_depth: int = 0

    def as_dict(self) -> dict[str, object]:
        return {"identity": self.identity, "lane": self.lane, "zone": self.zone, "priority": self.priority,
                "objective": self.objective, "conflict_keys": list(self.conflict_keys),
                "prerequisites": list(self.prerequisites), "evidence": list(self.evidence),
                "verification_paths": list(self.verification_paths), "readiness": self.readiness,
                "decision_score": self.decision_score, "topology_confidence": self.topology_confidence,
                "blast_radius": self.blast_radius, "critical_path_depth": self.critical_path_depth}


@dataclass(frozen=True, slots=True)
class WorkGraph:
    nodes: tuple[WorkNode, ...]
    _ordered_nodes: tuple[WorkNode, ...] = field(init=False, repr=False, compare=False)
    _by_identity: dict[str, WorkNode] = field(init=False, repr=False, compare=False)
    _depth: dict[str, int] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        ordered = tuple(sorted(self.nodes, key=lambda item: (-item.priority, item.identity)))
        identities = {item.identity for item in ordered}
        if len(identities) != len(ordered):
            raise ValueError("work graph contains duplicate identities")
        by_identity = {item.identity: item for item in ordered}
        for node in ordered:
            if any(item not in by_identity for item in node.prerequisites):
                raise ValueError(f"work graph has unknown prerequisites for {node.identity}")
        visiting: set[str] = set()
        visited: set[str] = set()
        depth: dict[str, int] = {}

        def visit(identity: str) -> int:
            if identity in visiting:
                raise ValueError(f"work graph contains prerequisite cycle at {identity}")
            if identity in visited:
                return depth[identity]
            visiting.add(identity)
            node_depth = 0
            for prerequisite in by_identity[identity].prerequisites:
                node_depth = max(node_depth, visit(prerequisite) + 1)
            visiting.remove(identity)
            visited.add(identity)
            depth[identity] = node_depth
            return node_depth

        for identity in by_identity:
            visit(identity)
        enriched = tuple(
            WorkNode(n.identity, n.lane, n.zone, n.priority, n.objective, n.conflict_keys, n.prerequisites,
                     n.evidence, n.verification_paths, n.readiness, n.decision_score,
                     n.topology_confidence, n.blast_radius, depth[n.identity])
            for n in ordered
        )
        object.__setattr__(self, "_ordered_nodes", enriched)
        object.__setattr__(self, "_by_identity", {n.identity: n for n in enriched})
        object.__setattr__(self, "_depth", depth)

    def as_dict(self) -> dict[str, object]:
        return {"nodes": [node.as_dict() for node in self._ordered_nodes],
                "frontier": [node.identity for node in self.frontier()],
                "critical_path_depth": max(self._depth.values(), default=0)}

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

    def frontier(self, completed: Iterable[str] = ()) -> tuple[WorkNode, ...]:
        done = set(completed)
        return tuple(node for node in self._ordered_nodes
                     if node.identity not in done and all(prerequisite in done for prerequisite in node.prerequisites))

    def critical_path(self) -> tuple[WorkNode, ...]:
        if not self._ordered_nodes:
            return ()
        terminal = max(self._ordered_nodes, key=lambda n: (self._depth[n.identity], n.priority, n.identity))
        path = [terminal]
        current = terminal
        while current.prerequisites:
            current = max((self._by_identity[p] for p in current.prerequisites),
                          key=lambda n: (self._depth[n.identity], n.priority, n.identity))
            path.append(current)
        return tuple(reversed(path))

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
            decision_score=candidate.decision_score, topology_confidence=candidate.topology_confidence,
            blast_radius=candidate.blast_radius,
        ))
    return WorkGraph(tuple(nodes))

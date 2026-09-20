"""Conflict-aware work graph derived from repository organization evidence."""
from __future__ import annotations

from dataclasses import dataclass
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
        for node in sorted(self.nodes, key=lambda item: (-item.priority, item.identity)):
            if any(prerequisite not in done for prerequisite in node.prerequisites):
                continue
            if any(key in conflicts for key in node.conflict_keys):
                continue
            ready.append(node)
            conflicts.update(node.conflict_keys)
            if len(ready) >= limit:
                break
        return tuple(ready)


def _conflicts(candidate: WorkCandidate) -> tuple[str, ...]:
    keys = {f"zone:{candidate.zone}", f"lane:{candidate.lane}"}
    if candidate.path:
        keys.add(f"path:{candidate.path}")
    return tuple(sorted(keys))


def build_work_graph(model: RepositoryModel, *, limit: int = 128) -> WorkGraph:
    candidates = derive_work_candidates(model, limit=limit)
    by_zone: dict[str, list[WorkCandidate]] = {}
    for candidate in candidates:
        by_zone.setdefault(candidate.zone, []).append(candidate)

    nodes: list[WorkNode] = []
    for candidate in candidates:
        prerequisites: list[str] = []
        zone_candidates = sorted(
            by_zone.get(candidate.zone, ()),
            key=lambda item: (-item.priority, item.identity),
        )
        higher = [
            item
            for item in zone_candidates
            if item.priority > candidate.priority
            and item.lane in {"repository-health", "architecture"}
        ]
        if candidate.lane not in {"repository-health", "architecture"} and higher:
            prerequisites.append(higher[0].identity)
        nodes.append(WorkNode(
            identity=candidate.identity,
            lane=candidate.lane,
            zone=candidate.zone,
            priority=candidate.priority,
            objective=candidate.objective,
            conflict_keys=_conflicts(candidate),
            prerequisites=tuple(sorted(set(prerequisites))),
            evidence=candidate.evidence,
        ))
    return WorkGraph(tuple(nodes))

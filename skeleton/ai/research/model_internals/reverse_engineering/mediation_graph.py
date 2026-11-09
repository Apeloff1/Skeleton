"""Directed mediation graphs for authorized causal-path summaries."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class MediationEdge:
    source: str
    target: str
    coefficient: float

    def __post_init__(self) -> None:
        if not self.source or not self.target:
            raise ReverseEngineeringError("mediation edge endpoints are required")
        if self.source == self.target:
            raise ReverseEngineeringError("mediation edge cannot self-loop")
        if not isfinite(self.coefficient):
            raise ReverseEngineeringError("mediation coefficient must be finite")


@dataclass(frozen=True)
class MediationPath:
    nodes: tuple[str, ...]
    path_effect: float


@dataclass(frozen=True)
class MediationGraphReport:
    source: str
    target: str
    node_count: int
    edge_count: int
    paths: tuple[MediationPath, ...]
    total_indirect_effect: float
    strongest_path: tuple[str, ...] | None
    strongest_absolute_effect: float
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "paths": [
                {"nodes": list(path.nodes), "path_effect": path.path_effect}
                for path in self.paths
            ],
            "total_indirect_effect": self.total_indirect_effect,
            "strongest_path": list(self.strongest_path) if self.strongest_path else None,
            "strongest_absolute_effect": self.strongest_absolute_effect,
            "digest": self.digest,
        }


def analyze_mediation_graph(
    edges: Sequence[MediationEdge],
    *,
    source: str,
    target: str,
    max_depth: int = 8,
) -> MediationGraphReport:
    if not edges:
        raise ReverseEngineeringError("mediation graph requires edges")
    if not source or not target or source == target:
        raise ReverseEngineeringError("mediation graph requires distinct source and target")
    if max_depth < 1:
        raise ReverseEngineeringError("max_depth must be positive")
    pairs = [(edge.source, edge.target) for edge in edges]
    if len(pairs) != len(set(pairs)):
        raise ReverseEngineeringError("mediation graph edges must be unique")

    adjacency: dict[str, list[MediationEdge]] = {}
    nodes = {source, target}
    for edge in edges:
        adjacency.setdefault(edge.source, []).append(edge)
        nodes.add(edge.source)
        nodes.add(edge.target)
    for values in adjacency.values():
        values.sort(key=lambda edge: (edge.target, edge.coefficient))

    paths: list[MediationPath] = []

    def walk(node: str, visited: tuple[str, ...], effect: float) -> None:
        if len(visited) > max_depth + 1:
            return
        if node == target:
            paths.append(MediationPath(nodes=visited, path_effect=effect))
            return
        for edge in adjacency.get(node, ()):
            if edge.target in visited:
                continue
            walk(edge.target, visited + (edge.target,), effect * edge.coefficient)

    walk(source, (source,), 1.0)
    ordered = tuple(sorted(paths, key=lambda path: (path.nodes, path.path_effect)))
    strongest = max(ordered, key=lambda path: (abs(path.path_effect), path.nodes)) if ordered else None
    payload = {
        "source": source,
        "target": target,
        "max_depth": max_depth,
        "edges": [
            {"source": edge.source, "target": edge.target, "coefficient": edge.coefficient}
            for edge in sorted(edges, key=lambda item: (item.source, item.target))
        ],
    }
    return MediationGraphReport(
        source=source,
        target=target,
        node_count=len(nodes),
        edge_count=len(edges),
        paths=ordered,
        total_indirect_effect=sum(path.path_effect for path in ordered),
        strongest_path=strongest.nodes if strongest else None,
        strongest_absolute_effect=abs(strongest.path_effect) if strongest else 0.0,
        digest=stable_digest(payload),
    )

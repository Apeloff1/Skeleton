"""Candidate circuit discovery from thresholded causal edges."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class CandidateEdge:
    source: str
    target: str
    effect: float
    replication_ratio: float
    sign_consistency: float

    def __post_init__(self) -> None:
        if not self.source or not self.target or self.source == self.target:
            raise ReverseEngineeringError("candidate edge requires distinct endpoints")
        if not isfinite(self.effect):
            raise ReverseEngineeringError("candidate edge effect must be finite")
        for value, name in (
            (self.replication_ratio, "replication_ratio"),
            (self.sign_consistency, "sign_consistency"),
        ):
            if not isfinite(value) or not 0.0 <= value <= 1.0:
                raise ReverseEngineeringError(f"{name} must be within [0, 1]")


@dataclass(frozen=True)
class CircuitCandidate:
    nodes: tuple[str, ...]
    edge_count: int
    weakest_absolute_effect: float
    mean_replication_ratio: float
    mean_sign_consistency: float
    score: float


@dataclass(frozen=True)
class CircuitDiscoveryReport:
    retained_edge_count: int
    candidate_count: int
    candidates: tuple[CircuitCandidate, ...]
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "retained_edge_count": self.retained_edge_count,
            "candidate_count": self.candidate_count,
            "candidates": [
                {
                    "nodes": list(candidate.nodes),
                    "edge_count": candidate.edge_count,
                    "weakest_absolute_effect": candidate.weakest_absolute_effect,
                    "mean_replication_ratio": candidate.mean_replication_ratio,
                    "mean_sign_consistency": candidate.mean_sign_consistency,
                    "score": candidate.score,
                }
                for candidate in self.candidates
            ],
            "digest": self.digest,
        }


def discover_circuit_candidates(
    edges: Sequence[CandidateEdge],
    *,
    source: str,
    target: str,
    minimum_absolute_effect: float = 0.1,
    minimum_replication_ratio: float = 0.75,
    minimum_sign_consistency: float = 0.75,
    max_depth: int = 6,
) -> CircuitDiscoveryReport:
    if not source or not target or source == target:
        raise ReverseEngineeringError("circuit discovery requires distinct source and target")
    if max_depth < 1:
        raise ReverseEngineeringError("max_depth must be positive")
    if minimum_absolute_effect < 0.0:
        raise ReverseEngineeringError("minimum_absolute_effect must be non-negative")
    retained = [
        edge
        for edge in edges
        if abs(edge.effect) >= minimum_absolute_effect
        and edge.replication_ratio >= minimum_replication_ratio
        and edge.sign_consistency >= minimum_sign_consistency
    ]
    adjacency: dict[str, list[CandidateEdge]] = {}
    for edge in retained:
        adjacency.setdefault(edge.source, []).append(edge)
    for values in adjacency.values():
        values.sort(key=lambda item: (item.target, -abs(item.effect)))

    candidates: list[CircuitCandidate] = []

    def walk(node: str, visited: tuple[str, ...], path_edges: tuple[CandidateEdge, ...]) -> None:
        if len(path_edges) > max_depth:
            return
        if node == target and path_edges:
            weakest = min(abs(edge.effect) for edge in path_edges)
            mean_rep = sum(edge.replication_ratio for edge in path_edges) / len(path_edges)
            mean_sign = sum(edge.sign_consistency for edge in path_edges) / len(path_edges)
            score = weakest * mean_rep * mean_sign
            candidates.append(
                CircuitCandidate(
                    nodes=visited,
                    edge_count=len(path_edges),
                    weakest_absolute_effect=weakest,
                    mean_replication_ratio=mean_rep,
                    mean_sign_consistency=mean_sign,
                    score=score,
                )
            )
            return
        for edge in adjacency.get(node, ()):
            if edge.target in visited:
                continue
            walk(edge.target, visited + (edge.target,), path_edges + (edge,))

    walk(source, (source,), ())
    ordered = tuple(sorted(candidates, key=lambda item: (-item.score, item.nodes)))
    payload = {
        "source": source,
        "target": target,
        "thresholds": {
            "minimum_absolute_effect": minimum_absolute_effect,
            "minimum_replication_ratio": minimum_replication_ratio,
            "minimum_sign_consistency": minimum_sign_consistency,
            "max_depth": max_depth,
        },
        "retained_edges": [
            {
                "source": edge.source,
                "target": edge.target,
                "effect": edge.effect,
                "replication_ratio": edge.replication_ratio,
                "sign_consistency": edge.sign_consistency,
            }
            for edge in sorted(retained, key=lambda item: (item.source, item.target))
        ],
    }
    return CircuitDiscoveryReport(
        retained_edge_count=len(retained),
        candidate_count=len(ordered),
        candidates=ordered,
        digest=stable_digest(payload),
    )

"""Causal circuit graph summaries from authorized intervention edges."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class CircuitEdgeObservation:
    observation_id: str
    probe_digest: str
    source_node: str
    target_node: str
    effect: float
    reproduced: bool = False

    def __post_init__(self) -> None:
        if not self.observation_id or not self.source_node or not self.target_node:
            raise ReverseEngineeringError("circuit edge identity fields are required")
        if self.source_node == self.target_node:
            raise ReverseEngineeringError("circuit edge cannot self-loop")
        if not is_sha256_digest(self.probe_digest):
            raise ReverseEngineeringError("probe_digest must be a sha256 hex digest")
        if not isfinite(self.effect):
            raise ReverseEngineeringError("circuit edge effect must be finite")


@dataclass(frozen=True)
class CircuitEdge:
    source_node: str
    target_node: str
    observation_count: int
    mean_effect: float
    mean_absolute_effect: float
    sign_consistency: float
    reproduction_ratio: float


@dataclass(frozen=True)
class CircuitGraphReport:
    node_count: int
    edge_count: int
    observation_count: int
    edges: tuple[CircuitEdge, ...]
    strongest_edge: tuple[str, str] | None
    strongest_mean_absolute_effect: float | None
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "observation_count": self.observation_count,
            "edges": [
                {
                    "source_node": edge.source_node,
                    "target_node": edge.target_node,
                    "observation_count": edge.observation_count,
                    "mean_effect": edge.mean_effect,
                    "mean_absolute_effect": edge.mean_absolute_effect,
                    "sign_consistency": edge.sign_consistency,
                    "reproduction_ratio": edge.reproduction_ratio,
                }
                for edge in self.edges
            ],
            "strongest_edge": list(self.strongest_edge) if self.strongest_edge else None,
            "strongest_mean_absolute_effect": self.strongest_mean_absolute_effect,
            "digest": self.digest,
        }


def build_circuit_graph(
    observations: Sequence[CircuitEdgeObservation],
) -> CircuitGraphReport:
    if not observations:
        raise ReverseEngineeringError("circuit graph requires observations")
    probe_digests = {item.probe_digest for item in observations}
    if len(probe_digests) != 1:
        raise ReverseEngineeringError("circuit observations must share probe_digest")
    grouped: dict[tuple[str, str], list[CircuitEdgeObservation]] = {}
    for item in observations:
        grouped.setdefault((item.source_node, item.target_node), []).append(item)

    edges: list[CircuitEdge] = []
    for (source, target), items in sorted(grouped.items()):
        effects = [item.effect for item in items]
        mean = sum(effects) / len(effects)
        if mean > 0:
            consistent = sum(value > 0 for value in effects) / len(effects)
        elif mean < 0:
            consistent = sum(value < 0 for value in effects) / len(effects)
        else:
            consistent = sum(value == 0 for value in effects) / len(effects)
        edges.append(
            CircuitEdge(
                source_node=source,
                target_node=target,
                observation_count=len(items),
                mean_effect=mean,
                mean_absolute_effect=sum(abs(value) for value in effects) / len(effects),
                sign_consistency=consistent,
                reproduction_ratio=sum(item.reproduced for item in items) / len(items),
            )
        )
    strongest = max(
        edges,
        key=lambda edge: (edge.mean_absolute_effect, edge.source_node, edge.target_node),
    )
    nodes = {item.source_node for item in observations} | {item.target_node for item in observations}
    payload = {
        "probe_digest": next(iter(probe_digests)),
        "observations": [
            {
                "observation_id": item.observation_id,
                "source_node": item.source_node,
                "target_node": item.target_node,
                "effect": item.effect,
                "reproduced": item.reproduced,
            }
            for item in sorted(observations, key=lambda value: value.observation_id)
        ],
    }
    return CircuitGraphReport(
        node_count=len(nodes),
        edge_count=len(edges),
        observation_count=len(observations),
        edges=tuple(edges),
        strongest_edge=(strongest.source_node, strongest.target_node),
        strongest_mean_absolute_effect=strongest.mean_absolute_effect,
        digest=stable_digest(payload),
    )

"""Deterministic graph-centrality summaries for reconstructed causal circuits."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class WeightedCircuitEdge:
    source: str
    target: str
    weight: float

    def __post_init__(self) -> None:
        if not self.source or not self.target:
            raise ReverseEngineeringError("weighted circuit edge endpoints are required")
        if self.source == self.target:
            raise ReverseEngineeringError("weighted circuit edge cannot self-loop")
        if self.weight < 0.0:
            raise ReverseEngineeringError("weighted circuit edge weight must be non-negative")


@dataclass(frozen=True)
class NodeCentrality:
    node: str
    in_degree: int
    out_degree: int
    inbound_weight: float
    outbound_weight: float
    total_weight: float


@dataclass(frozen=True)
class CircuitCentralityReport:
    node_count: int
    edge_count: int
    nodes: tuple[NodeCentrality, ...]
    highest_total_weight_node: str
    highest_total_weight: float
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "nodes": [
                {
                    "node": item.node,
                    "in_degree": item.in_degree,
                    "out_degree": item.out_degree,
                    "inbound_weight": item.inbound_weight,
                    "outbound_weight": item.outbound_weight,
                    "total_weight": item.total_weight,
                }
                for item in self.nodes
            ],
            "highest_total_weight_node": self.highest_total_weight_node,
            "highest_total_weight": self.highest_total_weight,
            "digest": self.digest,
        }


def analyze_circuit_centrality(
    edges: Sequence[WeightedCircuitEdge],
) -> CircuitCentralityReport:
    if not edges:
        raise ReverseEngineeringError("circuit centrality requires edges")
    pairs = [(edge.source, edge.target) for edge in edges]
    if len(pairs) != len(set(pairs)):
        raise ReverseEngineeringError("weighted circuit edges must be unique")
    nodes = sorted({node for pair in pairs for node in pair})
    incoming: dict[str, list[WeightedCircuitEdge]] = {node: [] for node in nodes}
    outgoing: dict[str, list[WeightedCircuitEdge]] = {node: [] for node in nodes}
    for edge in edges:
        outgoing[edge.source].append(edge)
        incoming[edge.target].append(edge)
    summaries = tuple(
        NodeCentrality(
            node=node,
            in_degree=len(incoming[node]),
            out_degree=len(outgoing[node]),
            inbound_weight=sum(edge.weight for edge in incoming[node]),
            outbound_weight=sum(edge.weight for edge in outgoing[node]),
            total_weight=sum(edge.weight for edge in incoming[node] + outgoing[node]),
        )
        for node in nodes
    )
    highest = max(summaries, key=lambda item: (item.total_weight, item.node))
    payload = {
        "edges": [
            {"source": edge.source, "target": edge.target, "weight": edge.weight}
            for edge in sorted(edges, key=lambda item: (item.source, item.target))
        ]
    }
    return CircuitCentralityReport(
        node_count=len(nodes),
        edge_count=len(edges),
        nodes=summaries,
        highest_total_weight_node=highest.node,
        highest_total_weight=highest.total_weight,
        digest=stable_digest(payload),
    )

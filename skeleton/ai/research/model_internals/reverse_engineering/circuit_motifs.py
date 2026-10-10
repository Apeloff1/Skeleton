"""Small causal-circuit motif summaries from directed edge sets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class DirectedCircuitEdge:
    source: str
    target: str

    def __post_init__(self) -> None:
        if not self.source or not self.target:
            raise ReverseEngineeringError("circuit edge endpoints are required")
        if self.source == self.target:
            raise ReverseEngineeringError("circuit edge cannot self-loop")


@dataclass(frozen=True)
class CircuitMotifReport:
    node_count: int
    edge_count: int
    chain_count: int
    fan_in_node_count: int
    fan_out_node_count: int
    reciprocal_pair_count: int
    source_count: int
    sink_count: int
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "chain_count": self.chain_count,
            "fan_in_node_count": self.fan_in_node_count,
            "fan_out_node_count": self.fan_out_node_count,
            "reciprocal_pair_count": self.reciprocal_pair_count,
            "source_count": self.source_count,
            "sink_count": self.sink_count,
            "digest": self.digest,
        }


def analyze_circuit_motifs(
    edges: Sequence[DirectedCircuitEdge],
) -> CircuitMotifReport:
    if not edges:
        raise ReverseEngineeringError("circuit motif analysis requires edges")
    pairs = [(edge.source, edge.target) for edge in edges]
    if len(pairs) != len(set(pairs)):
        raise ReverseEngineeringError("circuit motif edges must be unique")
    nodes = {node for pair in pairs for node in pair}
    outgoing: dict[str, set[str]] = {node: set() for node in nodes}
    incoming: dict[str, set[str]] = {node: set() for node in nodes}
    for source, target in pairs:
        outgoing[source].add(target)
        incoming[target].add(source)
    chain_count = 0
    for middle in nodes:
        chain_count += len(incoming[middle]) * len(outgoing[middle])
    reciprocal = sum(
        1
        for source, target in pairs
        if source < target and (target, source) in set(pairs)
    )
    payload = {
        "edges": [
            {"source": source, "target": target}
            for source, target in sorted(pairs)
        ]
    }
    return CircuitMotifReport(
        node_count=len(nodes),
        edge_count=len(pairs),
        chain_count=chain_count,
        fan_in_node_count=sum(len(incoming[node]) >= 2 for node in nodes),
        fan_out_node_count=sum(len(outgoing[node]) >= 2 for node in nodes),
        reciprocal_pair_count=reciprocal,
        source_count=sum(len(incoming[node]) == 0 and len(outgoing[node]) > 0 for node in nodes),
        sink_count=sum(len(outgoing[node]) == 0 and len(incoming[node]) > 0 for node in nodes),
        digest=stable_digest(payload),
    )

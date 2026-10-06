"""Deterministic NUMA placement with content-addressed replay evidence."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Iterable

from skeleton.contracts.canonical import canonical_json_bytes


def _digest(payload: object) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


@dataclass(frozen=True)
class NUMANode:
    node_id: int
    cpus: frozenset[int]
    memory: int


@dataclass(frozen=True)
class NUMAAffinity:
    cpu: int
    preferred_node: int


@dataclass(frozen=True)
class NUMAPlacement:
    node: int | None
    fallback: bool


@dataclass(frozen=True)
class NUMAPlacementReceipt:
    topology_digest: str
    request_digest: str
    decision_digest: str
    placement: NUMAPlacement

    def verify(self, nodes: Iterable[NUMANode], affinity: NUMAAffinity, required_memory: int) -> bool:
        fresh = place_with_receipt(nodes, affinity, required_memory)
        return fresh == self


def _normalized(nodes: Iterable[NUMANode]) -> tuple[NUMANode, ...]:
    result = tuple(sorted(tuple(nodes), key=lambda node: node.node_id))
    ids = [node.node_id for node in result]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate NUMA node")
    owned: set[int] = set()
    for node in result:
        if (
            isinstance(node.node_id, bool)
            or not isinstance(node.node_id, int)
            or node.node_id < 0
            or isinstance(node.memory, bool)
            or not isinstance(node.memory, int)
            or node.memory < 0
            or any(isinstance(cpu, bool) or not isinstance(cpu, int) or cpu < 0 for cpu in node.cpus)
        ):
            raise ValueError("invalid NUMA topology")
        overlap = owned.intersection(node.cpus)
        if overlap:
            raise ValueError("CPU cannot belong to multiple NUMA nodes")
        owned.update(node.cpus)
    return result


def _request(affinity: NUMAAffinity, required_memory: int) -> dict[str, int]:
    if (
        isinstance(required_memory, bool)
        or not isinstance(required_memory, int)
        or required_memory <= 0
        or isinstance(affinity.cpu, bool)
        or not isinstance(affinity.cpu, int)
        or affinity.cpu < 0
        or isinstance(affinity.preferred_node, bool)
        or not isinstance(affinity.preferred_node, int)
        or affinity.preferred_node < 0
    ):
        raise ValueError("valid NUMA request required")
    return {"cpu": affinity.cpu, "preferred_node": affinity.preferred_node, "required_memory": required_memory}


def place(nodes: Iterable[NUMANode], affinity: NUMAAffinity, required_memory: int) -> NUMAPlacement:
    normalized = _normalized(nodes)
    _request(affinity, required_memory)
    preferred = next(
        (
            node
            for node in normalized
            if node.node_id == affinity.preferred_node
            and affinity.cpu in node.cpus
            and node.memory >= required_memory
        ),
        None,
    )
    if preferred:
        return NUMAPlacement(preferred.node_id, False)
    candidates = [node for node in normalized if node.memory >= required_memory]
    return NUMAPlacement(candidates[0].node_id, True) if candidates else NUMAPlacement(None, True)


def place_with_receipt(nodes: Iterable[NUMANode], affinity: NUMAAffinity, required_memory: int) -> NUMAPlacementReceipt:
    normalized = _normalized(nodes)
    request = _request(affinity, required_memory)
    topology = [
        {"node_id": node.node_id, "cpus": sorted(node.cpus), "memory": node.memory}
        for node in normalized
    ]
    placement = place(normalized, affinity, required_memory)
    topology_digest = _digest(topology)
    request_digest = _digest(request)
    decision_digest = _digest({
        "topology_digest": topology_digest,
        "request_digest": request_digest,
        "node": placement.node,
        "fallback": placement.fallback,
    })
    return NUMAPlacementReceipt(topology_digest, request_digest, decision_digest, placement)

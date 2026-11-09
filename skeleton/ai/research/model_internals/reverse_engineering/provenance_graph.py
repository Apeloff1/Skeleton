"""Provenance DAG verification for reports, claims, and replication artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class ProvenanceNode:
    node_id: str
    kind: str
    digest: str
    parent_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.node_id or not self.kind:
            raise ReverseEngineeringError("provenance node identity is required")
        if not is_sha256_digest(self.digest):
            raise ReverseEngineeringError("provenance node digest must be sha256 hex")
        if len(self.parent_ids) != len(set(self.parent_ids)):
            raise ReverseEngineeringError("provenance parents must be unique")
        if self.node_id in self.parent_ids:
            raise ReverseEngineeringError("provenance node cannot parent itself")


@dataclass(frozen=True)
class ProvenanceGraphReport:
    node_count: int
    root_count: int
    leaf_count: int
    max_depth: int
    cycle_free: bool
    missing_parent_count: int
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "node_count": self.node_count,
            "root_count": self.root_count,
            "leaf_count": self.leaf_count,
            "max_depth": self.max_depth,
            "cycle_free": self.cycle_free,
            "missing_parent_count": self.missing_parent_count,
            "digest": self.digest,
        }


def verify_provenance_graph(
    nodes: Sequence[ProvenanceNode],
) -> ProvenanceGraphReport:
    if not nodes:
        raise ReverseEngineeringError("provenance graph requires nodes")
    ids = [node.node_id for node in nodes]
    if len(ids) != len(set(ids)):
        raise ReverseEngineeringError("provenance node ids must be unique")
    by_id = {node.node_id: node for node in nodes}
    missing = sum(parent not in by_id for node in nodes for parent in node.parent_ids)
    children: dict[str, set[str]] = {node.node_id: set() for node in nodes}
    for node in nodes:
        for parent in node.parent_ids:
            if parent in children:
                children[parent].add(node.node_id)

    state: dict[str, int] = {}
    depths: dict[str, int] = {}
    cycle = False

    def visit(node_id: str) -> int:
        nonlocal cycle
        marker = state.get(node_id, 0)
        if marker == 1:
            cycle = True
            return 0
        if marker == 2:
            return depths[node_id]
        state[node_id] = 1
        node = by_id[node_id]
        parent_depths = [visit(parent) for parent in node.parent_ids if parent in by_id]
        depth = (max(parent_depths) + 1) if parent_depths else 0
        state[node_id] = 2
        depths[node_id] = depth
        return depth

    for node_id in sorted(by_id):
        visit(node_id)
    payload = {
        "nodes": [
            {
                "node_id": node.node_id,
                "kind": node.kind,
                "digest": node.digest,
                "parent_ids": list(node.parent_ids),
            }
            for node in sorted(nodes, key=lambda value: value.node_id)
        ]
    }
    return ProvenanceGraphReport(
        node_count=len(nodes),
        root_count=sum(not node.parent_ids for node in nodes),
        leaf_count=sum(not children[node.node_id] for node in nodes),
        max_depth=max(depths.values()) if depths else 0,
        cycle_free=not cycle,
        missing_parent_count=missing,
        digest=stable_digest(payload),
    )

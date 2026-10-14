"""Lineage completeness checks from evidence through claim to replication."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class LineageNode:
    node_id: str
    kind: str
    digest: str
    parent_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.node_id or not self.kind:
            raise ReverseEngineeringError("lineage node identity is required")
        if self.kind not in {"evidence", "analysis", "claim", "replication"}:
            raise ReverseEngineeringError("invalid lineage node kind")
        if not is_sha256_digest(self.digest):
            raise ReverseEngineeringError("lineage digest must be sha256 hex")
        if len(self.parent_ids) != len(set(self.parent_ids)):
            raise ReverseEngineeringError("lineage parent ids must be unique")
        if self.node_id in self.parent_ids:
            raise ReverseEngineeringError("lineage node cannot parent itself")


@dataclass(frozen=True)
class LineageClosureReport:
    node_count: int
    evidence_count: int
    analysis_count: int
    claim_count: int
    replication_count: int
    missing_parent_count: int
    claim_without_evidence_count: int
    supported_claim_without_replication_count: int
    closed_claim_count: int
    fully_closed: bool
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "node_count": self.node_count,
            "evidence_count": self.evidence_count,
            "analysis_count": self.analysis_count,
            "claim_count": self.claim_count,
            "replication_count": self.replication_count,
            "missing_parent_count": self.missing_parent_count,
            "claim_without_evidence_count": self.claim_without_evidence_count,
            "supported_claim_without_replication_count": self.supported_claim_without_replication_count,
            "closed_claim_count": self.closed_claim_count,
            "fully_closed": self.fully_closed,
            "digest": self.digest,
        }


def analyze_lineage_closure(
    nodes: Sequence[LineageNode],
    *,
    supported_claim_ids: Sequence[str] = (),
) -> LineageClosureReport:
    if not nodes:
        raise ReverseEngineeringError("lineage closure requires nodes")
    ids = [node.node_id for node in nodes]
    if len(ids) != len(set(ids)):
        raise ReverseEngineeringError("lineage node ids must be unique")
    by_id = {node.node_id: node for node in nodes}
    missing = sum(parent not in by_id for node in nodes for parent in node.parent_ids)

    ancestry_cache: dict[str, set[str]] = {}
    def ancestry(node_id: str, active: set[str] | None = None) -> set[str]:
        if node_id in ancestry_cache:
            return ancestry_cache[node_id]
        active = set() if active is None else set(active)
        if node_id in active:
            raise ReverseEngineeringError("lineage graph contains a cycle")
        active.add(node_id)
        node = by_id[node_id]
        result: set[str] = set()
        for parent in node.parent_ids:
            if parent not in by_id:
                continue
            result.add(parent)
            result.update(ancestry(parent, active))
        ancestry_cache[node_id] = result
        return result

    claims = [node for node in nodes if node.kind == "claim"]
    replications = [node for node in nodes if node.kind == "replication"]
    supported = set(supported_claim_ids)
    unknown_supported = supported - {claim.node_id for claim in claims}
    if unknown_supported:
        raise ReverseEngineeringError("supported_claim_ids contains unknown claim ids")

    claim_without_evidence = 0
    closed = 0
    supported_without_replication = 0
    for claim in claims:
        ancestors = ancestry(claim.node_id)
        has_evidence = any(by_id[node_id].kind == "evidence" for node_id in ancestors)
        if not has_evidence:
            claim_without_evidence += 1
        has_replication = any(
            claim.node_id in ancestry(replication.node_id)
            for replication in replications
        )
        if claim.node_id in supported and not has_replication:
            supported_without_replication += 1
        if has_evidence and (claim.node_id not in supported or has_replication):
            closed += 1

    payload = {
        "supported_claim_ids": sorted(supported),
        "nodes": [
            {
                "node_id": node.node_id,
                "kind": node.kind,
                "digest": node.digest,
                "parent_ids": list(node.parent_ids),
            }
            for node in sorted(nodes, key=lambda value: value.node_id)
        ],
    }
    return LineageClosureReport(
        node_count=len(nodes),
        evidence_count=sum(node.kind == "evidence" for node in nodes),
        analysis_count=sum(node.kind == "analysis" for node in nodes),
        claim_count=len(claims),
        replication_count=len(replications),
        missing_parent_count=missing,
        claim_without_evidence_count=claim_without_evidence,
        supported_claim_without_replication_count=supported_without_replication,
        closed_claim_count=closed,
        fully_closed=(missing == 0 and claim_without_evidence == 0 and supported_without_replication == 0),
        digest=stable_digest(payload),
    )

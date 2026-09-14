"""Evidence-independence analyzer for empirical verification.

A verifier must not count five papers derived from one dataset as five independent
confirmations. This module derives conservative dependence clusters from explicit
source lineage, shared content digests and declared independence groups. It never
invents independence: uncertain lineage remains visible as a diagnostic rather
than being upgraded to independent support.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
from typing import Iterable

from core.source_lineage import SourceLineageGraph, SourceNode
from core.truth_verifier import EvidenceItem


@dataclass(frozen=True, slots=True)
class IndependenceCluster:
    id: str
    source_ids: tuple[str, ...]
    reasons: tuple[str, ...]
    shared_roots: tuple[str, ...]
    shared_content_sha256: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class IndependenceReport:
    raw_sources: int
    effective_independent_sources: int
    clusters: tuple[IndependenceCluster, ...]
    unresolved_sources: tuple[str, ...]
    attestation_sha256: str


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


class SourceIndependenceAnalyzer:
    def __init__(self, lineage: SourceLineageGraph) -> None:
        self.lineage = lineage

    def _ancestry(self, source_id: str) -> tuple[set[str], set[str], SourceNode | None]:
        node = self.lineage.get(source_id)
        if node is None:
            return set(), set(), None
        seen: set[str] = set()
        roots: set[str] = set()
        stack = list(node.parent_ids)
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            parent = self.lineage.get(current)
            if parent is None:
                roots.add(current)
                continue
            if parent.parent_ids:
                stack.extend(parent.parent_ids)
            else:
                roots.add(parent.source_id)
        if not node.parent_ids:
            roots.add(node.source_id)
        return seen, roots, node

    @staticmethod
    def _union(parent: dict[str, str], a: str, b: str) -> None:
        def root(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        ra, rb = root(a), root(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    def analyze(self, evidence: Iterable[EvidenceItem]) -> IndependenceReport:
        rows = tuple(evidence)
        source_ids = tuple(dict.fromkeys(item.source_id for item in rows if item.source_id))
        parent = {source_id: source_id for source_id in source_ids}
        ancestry: dict[str, set[str]] = {}
        roots: dict[str, set[str]] = {}
        nodes: dict[str, SourceNode | None] = {}
        unresolved: list[str] = []
        by_group: dict[str, list[str]] = {}
        by_digest: dict[str, list[str]] = {}

        for item in rows:
            if not item.source_id:
                continue
            ancestors, source_roots, node = self._ancestry(item.source_id)
            ancestry[item.source_id] = ancestors
            roots[item.source_id] = source_roots
            nodes[item.source_id] = node
            if node is None:
                unresolved.append(item.source_id)
            if item.independence_group:
                by_group.setdefault(item.independence_group, []).append(item.source_id)
            if node is not None and node.content_sha256:
                by_digest.setdefault(node.content_sha256, []).append(item.source_id)

        for members in (*by_group.values(), *by_digest.values()):
            unique = tuple(dict.fromkeys(members))
            for other in unique[1:]:
                self._union(parent, unique[0], other)

        ids = list(source_ids)
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                # Direct ancestry or any shared upstream root means the evidence is
                # not independent for replication counting.
                if a in ancestry.get(b, set()) or b in ancestry.get(a, set()):
                    self._union(parent, a, b)
                    continue
                common_roots = roots.get(a, set()) & roots.get(b, set())
                if common_roots:
                    self._union(parent, a, b)

        def find(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        grouped: dict[str, list[str]] = {}
        for source_id in source_ids:
            grouped.setdefault(find(source_id), []).append(source_id)

        clusters: list[IndependenceCluster] = []
        for members in sorted((tuple(sorted(v)) for v in grouped.values()), key=lambda x: x):
            shared_roots = set.intersection(*(roots.get(x, set()) for x in members)) if len(members) > 1 else set()
            digests = {nodes[x].content_sha256 for x in members if nodes.get(x) is not None and nodes[x].content_sha256}
            reasons: list[str] = []
            if len(members) > 1:
                member_items = [item for item in rows if item.source_id in members]
                groups = {item.independence_group for item in member_items if item.independence_group}
                if len(groups) == 1 and groups:
                    reasons.append("declared_independence_group_shared")
                if shared_roots:
                    reasons.append("shared_upstream_source")
                if len(digests) == 1 and digests:
                    reasons.append("identical_content_digest")
                if any(a in ancestry.get(b, set()) or b in ancestry.get(a, set()) for a in members for b in members if a != b):
                    reasons.append("direct_source_derivation")
            cluster_id = "ind-" + _sha({"sources": members, "roots": sorted(shared_roots), "digests": sorted(digests)})[:20]
            clusters.append(IndependenceCluster(cluster_id, members, tuple(dict.fromkeys(reasons)), tuple(sorted(shared_roots)), tuple(sorted(digests))))

        payload = {
            "raw_sources": len(source_ids),
            "effective_independent_sources": len(clusters),
            "clusters": [cluster.__dict__ if hasattr(cluster, "__dict__") else {
                "id": cluster.id, "source_ids": cluster.source_ids, "reasons": cluster.reasons,
                "shared_roots": cluster.shared_roots, "shared_content_sha256": cluster.shared_content_sha256,
            } for cluster in clusters],
            "unresolved_sources": tuple(sorted(set(unresolved))),
        }
        return IndependenceReport(
            raw_sources=len(source_ids), effective_independent_sources=len(clusters),
            clusters=tuple(clusters), unresolved_sources=tuple(sorted(set(unresolved))),
            attestation_sha256=_sha(payload),
        )

    def collapse(self, evidence: Iterable[EvidenceItem]) -> tuple[tuple[EvidenceItem, ...], IndependenceReport]:
        rows = tuple(evidence)
        report = self.analyze(rows)
        cluster_for: dict[str, str] = {}
        for cluster in report.clusters:
            for source_id in cluster.source_ids:
                cluster_for[source_id] = cluster.id
        collapsed = tuple(
            replace(item, independence_group=cluster_for.get(item.source_id, item.independence_group))
            for item in rows
        )
        return collapsed, report

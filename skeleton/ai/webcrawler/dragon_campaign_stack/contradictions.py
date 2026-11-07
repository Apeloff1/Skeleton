"""Bounded, human-review-only disagreement graph for attributed claim readings.

The graph does not perform semantic entailment. It records declared opposing
stances from exact current citations, detects circular citation dependencies,
and suggests targeted rereads without manufacturing knowledge or trust.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from .claims import ClaimReviewMatrix, ClaimCitation
from .contracts import digest, exact_digest, finite, integer


@dataclass(frozen=True)
class Disagreement:
    claim_id: str
    support_source_ids: tuple[str, ...]
    refute_source_ids: tuple[str, ...]
    shared_source_ids: tuple[str, ...]
    independent_group_count: int
    severity: str
    needs_review: bool = True


@dataclass(frozen=True)
class CitationDependency:
    citing_source_id: str
    cited_source_id: str
    relation: str

    def __post_init__(self):
        exact_digest(self.citing_source_id, "citing source")
        exact_digest(self.cited_source_id, "cited source")
        if self.citing_source_id == self.cited_source_id:
            raise ValueError("self citation dependency")
        if self.relation not in ("quotes", "mirrors", "summarizes", "syndicates"):
            raise ValueError("unknown citation dependency")


@dataclass(frozen=True)
class DisagreementGraph:
    claim_count: int
    disagreements: tuple[Disagreement, ...]
    cited_source_count: int
    dependency_edges: tuple[CitationDependency, ...]
    dependent_components: tuple[tuple[str, ...], ...]
    review_order: tuple[str, ...]
    graph_digest: str
    claims_resolved: bool = False


def _components(
    source_ids: tuple[str, ...],
    edges: tuple[CitationDependency, ...],
) -> tuple[tuple[str, ...], ...]:
    """Undirected connected components flag sources sharing provenance."""
    parent = {source: source for source in source_ids}
    def root(item: str) -> str:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item
    for edge in edges:
        a, b = root(edge.citing_source_id), root(edge.cited_source_id)
        if a != b:
            parent[max(a, b)] = min(a, b)
    groups: dict[str, list[str]] = {}
    for source in source_ids:
        groups.setdefault(root(source), []).append(source)
    return tuple(sorted(tuple(sorted(x)) for x in groups.values() if len(x) > 1))


def build_disagreement_graph(
    matrix: ClaimReviewMatrix,
    *,
    dependencies: Iterable[CitationDependency] = (),
    max_edges: int = 256,
) -> DisagreementGraph:
    if not isinstance(matrix, ClaimReviewMatrix):
        raise TypeError("typed claim assessment required")
    integer(max_edges, "dependency edge limit", 0, 512)
    edges = tuple(dependencies)
    if len(edges) > max_edges or len(set(edges)) != len(edges):
        raise ValueError("duplicated or oversized citation graph")
    sources = set()
    for claim in matrix.claims:
        sources.update(claim.support_sources)
        sources.update(claim.refute_sources)
        sources.update(claim.context_sources)
    for edge in edges:
        if not isinstance(edge, CitationDependency):
            raise TypeError("typed citation edge required")
        if edge.citing_source_id not in sources or edge.cited_source_id not in sources:
            raise ValueError("dependency references unadmitted source")
    grouped = _components(tuple(sorted(sources)), edges)
    conflicts = []
    for claim in matrix.claims:
        support = set(claim.support_sources)
        refute = set(claim.refute_sources)
        overlap = support & refute
        if not claim.conflicted and not overlap:
            continue
        independence = min(
            claim.attested_support_groups,
            claim.attested_refute_groups,
        )
        severity = (
            "critical" if independence >= 2 else
            "high" if support and refute else
            "medium"
        )
        conflicts.append(Disagreement(
            claim_id=claim.claim_id,
            support_source_ids=tuple(sorted(support)),
            refute_source_ids=tuple(sorted(refute)),
            shared_source_ids=tuple(sorted(overlap)),
            independent_group_count=independence,
            severity=severity,
        ))
    conflicts.sort(key=lambda x: (
        {"critical": 0, "high": 1, "medium": 2}[x.severity],
        -x.independent_group_count, x.claim_id,
    ))
    payload = {
        "matrix": matrix.matrix_digest,
        "conflicts": [asdict(x) for x in conflicts],
        "dependencies": [asdict(x) for x in edges],
        "components": grouped,
    }
    return DisagreementGraph(
        claim_count=len(matrix.claims),
        disagreements=tuple(conflicts),
        cited_source_count=len(sources),
        dependency_edges=tuple(sorted(edges, key=lambda x: (
            x.citing_source_id, x.cited_source_id, x.relation
        ))),
        dependent_components=grouped,
        review_order=tuple(x.claim_id for x in conflicts),
        graph_digest=digest(payload),
    )

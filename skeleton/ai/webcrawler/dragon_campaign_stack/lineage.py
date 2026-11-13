"""Bounded provenance graph and revision invalidation for Dragon captures.

Dependency graph operations are purely diagnostic. No inference of legal
rights, factual corroboration, training permission or source independence
is derived from URL overlap.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from .contracts import CampaignLimits, digest, exact_digest


@dataclass(frozen=True)
class SourceLink:
    child_source_id: str
    parent_source_id: str
    relation: str

    def __post_init__(self) -> None:
        exact_digest(self.child_source_id, "child")
        exact_digest(self.parent_source_id, "parent")
        if self.child_source_id == self.parent_source_id:
            raise ValueError("self provenance link")
        if self.relation not in ("derived_from", "cites", "revision_of", "same_content"):
            raise ValueError("unknown provenance relationship")


@dataclass(frozen=True)
class LineageImpact:
    revoked_source_ids: tuple[str, ...]
    affected_source_ids: tuple[str, ...]
    invalidated_links: tuple[SourceLink, ...]
    unaffected_source_ids: tuple[str, ...]
    lineage_digest: str


@dataclass(frozen=True)
class DuplicateFamily:
    content_hash: str
    source_ids: tuple[str, ...]


def validate_lineage(
    source_ids: Iterable[str],
    links: Iterable[SourceLink], *,
    limits: CampaignLimits = CampaignLimits(),
) -> tuple[SourceLink, ...]:
    vertices = tuple(source_ids)
    if len(vertices) > 128 or len(set(vertices)) != len(vertices):
        raise ValueError("duplicate or oversized source universe")
    for x in vertices:
        exact_digest(x, "source id")
    edges = tuple(links)
    if len(edges) > limits.max_dependency_edges:
        raise ValueError("dependency edge capacity exceeded")
    known = set(vertices)
    for x in edges:
        if not isinstance(x, SourceLink):
            raise ValueError("untyped provenance relation")
        if x.child_source_id not in known or x.parent_source_id not in known:
            raise ValueError("dangling provenance relation")
    if len(set(edges)) != len(edges):
        raise ValueError("duplicate provenance relation")
    # Citation and same-content links are not dependency edges; cycles of
    # citations are normal. "derived_from" and "revision_of" must be acyclic.
    children: dict[str, set[str]] = {vertex: set() for vertex in known}
    for edge in edges:
        if edge.relation in ("derived_from", "revision_of"):
            children[edge.parent_source_id].add(edge.child_source_id)
    state: dict[str, int] = {}
    def visit(node: str) -> None:
        if state.get(node) == 1:
            raise ValueError("cyclic source derivation")
        if state.get(node) == 2:
            return
        state[node] = 1
        for child in sorted(children[node]):
            visit(child)
        state[node] = 2
    for node in sorted(known):
        visit(node)
    return tuple(sorted(
        edges,
        key=lambda e: (e.child_source_id, e.parent_source_id, e.relation),
    ))


def invalidation_closure(
    source_ids: Iterable[str], links: Iterable[SourceLink], *,
    revoked: Iterable[str],
    limits: CampaignLimits = CampaignLimits(),
) -> LineageImpact:
    ids = tuple(source_ids)
    edges = validate_lineage(ids, links, limits=limits)
    revoked_set = set(revoked)
    if not revoked_set.issubset(ids):
        raise ValueError("revocation refers to unknown source")
    affected = set(revoked_set)
    descendants: dict[str, set[str]] = {source_id: set() for source_id in ids}
    for edge in edges:
        if edge.relation in ("derived_from", "revision_of"):
            descendants[edge.parent_source_id].add(edge.child_source_id)
    stack = sorted(affected)
    while stack:
        for child in sorted(descendants[stack.pop()]):
            if child not in affected:
                affected.add(child)
                stack.append(child)
    touched = tuple(e for e in edges if e.child_source_id in affected or e.parent_source_id in affected)
    payload = {
        "sources": sorted(ids), "revoked": sorted(revoked_set),
        "affected": sorted(affected), "edges": [asdict(x) for x in touched],
    }
    return LineageImpact(
        tuple(sorted(revoked_set)), tuple(sorted(affected)),
        touched, tuple(sorted(set(ids) - affected)), digest(payload),
    )


def exact_duplicate_families(
    sources: Iterable[tuple[str, str]], *, maximum: int = 128,
) -> tuple[DuplicateFamily, ...]:
    if type(maximum) is not int or not 1 <= maximum <= 128:
        raise ValueError("invalid duplicate scan capacity")
    rows = tuple(sources)
    if len(rows) > maximum:
        raise ValueError("duplicate scan capacity exceeded")
    hashes: dict[str, list[str]] = {}
    seen = set()
    for source_id, content_hash in rows:
        exact_digest(source_id, "source")
        exact_digest(content_hash, "content")
        if source_id in seen:
            raise ValueError("duplicate source identity")
        seen.add(source_id)
        hashes.setdefault(content_hash, []).append(source_id)
    return tuple(
        DuplicateFamily(key, tuple(sorted(ids)))
        for key, ids in sorted(hashes.items())
        if len(ids) > 1
    )

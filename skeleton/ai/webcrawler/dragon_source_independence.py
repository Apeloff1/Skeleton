"""Provenance-derived dependency clustering for repeated source analysis.

Do not trust a caller-provided independence label as statistical independence.
This conservative union-find groups observations when any declared lineage,
content identity, canonical origin, or derivation relationship overlaps.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from urllib.parse import urlsplit, urlunsplit


@dataclass(frozen=True)
class SourceProvenance:
    source_id: str
    content_digest: str
    canonical_uri: str
    parent_source_ids: tuple[str, ...] = ()
    lineage_tokens: tuple[str, ...] = ()


@dataclass(frozen=True)
class DependencyCluster:
    cluster_id: str
    source_ids: tuple[str, ...]
    reasons: tuple[str, ...]


def _uri_identity(uri: str) -> str:
    parts = urlsplit(uri)
    host = (parts.hostname or "").lower()
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), host, path, "", ""))


def derive_dependency_clusters(
    sources: tuple[SourceProvenance, ...], *, authorized: bool,
    max_sources: int = 10000,
) -> tuple[DependencyCluster, ...]:
    if not authorized:
        raise PermissionError("provenance clustering requires authorization")
    if not 1 <= max_sources <= 100000:
        raise ValueError("invalid source budget")
    if len(sources) > max_sources:
        raise ValueError("source budget exceeded")
    by_id = {}
    for source in sources:
        if not source.source_id or source.source_id in by_id:
            raise ValueError("source IDs must be non-empty and unique")
        if len(source.content_digest) != 64 or any(
            c not in "0123456789abcdef" for c in source.content_digest
        ):
            raise ValueError("invalid content digest")
        if not source.canonical_uri:
            raise ValueError("canonical URI required")
        by_id[source.source_id] = source
    parent = {x.source_id: x.source_id for x in sources}
    reasons = {x.source_id: set() for x in sources}
    def root(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a, b, reason):
        ra, rb = root(a), root(b)
        if ra != rb:
            parent[rb] = ra
        reasons[a].add(reason)
        reasons[b].add(reason)
    content, uri, lineage = {}, {}, {}
    for source in sources:
        for key, table, reason in (
            (source.content_digest, content, "identical_content"),
            (_uri_identity(source.canonical_uri), uri, "canonical_origin"),
        ):
            if key in table:
                union(source.source_id, table[key], reason)
            else:
                table[key] = source.source_id
        for token in source.lineage_tokens:
            if token in lineage:
                union(source.source_id, lineage[token], "shared_lineage")
            else:
                lineage[token] = source.source_id
        for parent_id in source.parent_source_ids:
            if parent_id not in by_id:
                raise ValueError("unknown parent source")
            union(source.source_id, parent_id, "declared_derivation")
    groups = {}
    for source in sources:
        groups.setdefault(root(source.source_id), []).append(source.source_id)
    result = []
    for members in groups.values():
        ordered = tuple(sorted(members))
        all_reasons = tuple(sorted(set().union(*(reasons[x] for x in ordered))))
        cluster_id = sha256("\0".join(ordered).encode()).hexdigest()
        result.append(DependencyCluster(cluster_id, ordered, all_reasons))
    return tuple(sorted(result, key=lambda x: x.source_ids))

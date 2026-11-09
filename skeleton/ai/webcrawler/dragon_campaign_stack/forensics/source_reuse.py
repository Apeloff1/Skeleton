"""Cross-host source reuse and direct-vs-transitive similarity lineage.

Exact content equality proves byte reuse, not factual truth. Near-duplicate
edges are review hypotheses. A transitive component never implies that any
two endpoints are directly similar or that provenance is established.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass

from ..contracts import digest, integer
from ..near_duplicate_audit import SourceSimilarityAudit
from .frames import FrameSet


@dataclass(frozen=True)
class ReuseComponent:
    source_ids: tuple[str, ...]
    hosts: tuple[str, ...]
    observed_direct_edges: int
    exact_content_pairs: int
    suspected_near_copy_pairs: int
    unobserved_pairs: int
    human_provenance_review_required: bool = True
    shared_origin_proven: bool = False


@dataclass(frozen=True)
class SourceReuseReport:
    frame_set_digest: str
    similarity_digest: str
    components: tuple[ReuseComponent, ...]
    selected_sources: tuple[str, ...]
    hosts_with_repeated_selection: tuple[str, ...]
    cross_host_review_components: int
    report_digest: str
    source_independence_certified: bool = False
    evidence_promoted: bool = False


def analyze_source_reuse(
    frames: FrameSet, similarity: SourceSimilarityAudit,
    *, max_sources: int = 32, max_edges: int = 496,
) -> SourceReuseReport:
    if not isinstance(frames, FrameSet) or not isinstance(similarity, SourceSimilarityAudit):
        raise TypeError("typed source-bound frames and similarity required")
    integer(max_sources, "source reuse cap", 1, 32)
    integer(max_edges, "source reuse edge cap", 0, 496)
    if (similarity.mandate_digest != frames.mandate_digest
            or similarity.source_snapshot_digest != frames.snapshot_digest
            or similarity.source_policy_digest != frames.policy_digest
            or similarity.retrieval_digest != frames.retrieval_digest
            or similarity.lineage_verified or similarity.factual_independence_certified
            or similarity.training_or_publication_granted):
        raise PermissionError("foreign or privileged source similarity receipt")
    selected = {x.anchor.source_id: x.anchor.host for x in frames.frames}
    if len(selected) > max_sources or len(similarity.similar_pairs) > max_edges:
        raise ValueError("source reuse analysis capacity exceeded")
    if not set(similarity.considered_source_ids).issubset(selected):
        raise PermissionError("similarity describes unselected source")
    links: dict[tuple[str, str], str] = {}
    for row in similarity.similar_pairs:
        a, b = row.left_source_id, row.right_source_id
        if a not in selected or b not in selected or a == b:
            raise PermissionError("similarity edge outside selected frame set")
        if row.left_host != selected[a] or row.right_host != selected[b]:
            raise PermissionError("similarity host identity changed")
        key = tuple(sorted((a, b)))
        if key in links:
            raise ValueError("duplicate similarity edge")
        if row.relation not in ("exact_content", "near_duplicate_review"):
            raise PermissionError("unsupported source lineage assertion")
        links[key] = row.relation
    parent = {source_id: source_id for source_id in selected}
    def root(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for a, b in sorted(links):
        aa, bb = root(a), root(b)
        if aa != bb:
            parent[max(aa, bb)] = min(aa, bb)
    buckets: dict[str, list[str]] = defaultdict(list)
    for source_id in sorted(selected):
        buckets[root(source_id)].append(source_id)
    results = []
    for ids in buckets.values():
        if len(ids) < 2:
            continue
        members = tuple(sorted(ids))
        component_edges = [kind for (a, b), kind in links.items()
                           if a in members and b in members]
        direct = len(component_edges)
        possible = len(members) * (len(members) - 1) // 2
        results.append(ReuseComponent(
            members, tuple(sorted({selected[x] for x in members})),
            direct, sum(x == "exact_content" for x in component_edges),
            sum(x == "near_duplicate_review" for x in component_edges),
            possible - direct,
        ))
    host_counts = defaultdict(int)
    for host in selected.values():
        host_counts[host] += 1
    results.sort(key=lambda r: r.source_ids)
    payload = {
        "frame_set": frames.frame_set_digest,
        "similarity": similarity.audit_digest,
        "components": [asdict(x) for x in results],
        "sources": sorted(selected),
        "host_counts": sorted(host_counts.items()),
    }
    return SourceReuseReport(
        frames.frame_set_digest, similarity.audit_digest, tuple(results),
        tuple(sorted(selected)),
        tuple(sorted(host for host, count in host_counts.items() if count > 1)),
        sum(len(row.hosts) > 1 for row in results),
        digest(payload),
    )

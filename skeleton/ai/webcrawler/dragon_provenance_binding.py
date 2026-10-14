"""Provenance-authoritative evidence preparation.

Rewrites caller-supplied independence labels using dependency clusters derived
from source provenance. Unknown evidence sources fail closed.
"""
from __future__ import annotations
from dataclasses import replace

from .dragon_probabilistic_distillation import EvidencePass
from .dragon_source_independence import SourceProvenance, derive_dependency_clusters


def bind_provenance_independence(
    evidence: tuple[EvidencePass, ...],
    provenance: tuple[SourceProvenance, ...], *,
    authorized: bool,
) -> tuple[EvidencePass, ...]:
    if not authorized:
        raise PermissionError("provenance binding requires authorization")
    clusters = derive_dependency_clusters(provenance, authorized=True)
    group_for = {
        source_id: cluster.cluster_id
        for cluster in clusters
        for source_id in cluster.source_ids
    }
    evidence_ids = {item.source_id for item in evidence}
    provenance_ids = {item.source_id for item in provenance}
    missing = evidence_ids - provenance_ids
    if missing:
        raise ValueError(
            "evidence missing provenance: " + ",".join(sorted(missing))
        )
    # Extra provenance is allowed: a capture inventory may contain sources
    # irrelevant to the current claim.
    return tuple(
        replace(item, independence_group=group_for[item.source_id])
        for item in evidence
    )

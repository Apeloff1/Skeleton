"""Stability metrics for repeated top-k attribution observations."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class AttributionSnapshot:
    snapshot_id: str
    probe_digest: str
    feature_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.snapshot_id:
            raise ReverseEngineeringError("attribution snapshot requires snapshot_id")
        if not is_sha256_digest(self.probe_digest):
            raise ReverseEngineeringError("probe_digest must be a sha256 hex digest")
        if not self.feature_ids:
            raise ReverseEngineeringError("feature_ids must be non-empty")
        if len(self.feature_ids) != len(set(self.feature_ids)):
            raise ReverseEngineeringError("feature_ids must be unique within a snapshot")


@dataclass(frozen=True)
class AttributionStabilityReport:
    snapshot_count: int
    unique_feature_count: int
    mean_pairwise_jaccard: float
    min_pairwise_jaccard: float
    universal_feature_count: int
    majority_feature_count: int
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "snapshot_count": self.snapshot_count,
            "unique_feature_count": self.unique_feature_count,
            "mean_pairwise_jaccard": self.mean_pairwise_jaccard,
            "min_pairwise_jaccard": self.min_pairwise_jaccard,
            "universal_feature_count": self.universal_feature_count,
            "majority_feature_count": self.majority_feature_count,
            "digest": self.digest,
        }


def analyze_attribution_stability(
    snapshots: Sequence[AttributionSnapshot],
) -> AttributionStabilityReport:
    if len(snapshots) < 2:
        raise ReverseEngineeringError("attribution stability requires at least two snapshots")
    ordered = sorted(snapshots, key=lambda item: item.snapshot_id)
    probe_digests = {item.probe_digest for item in ordered}
    if len(probe_digests) != 1:
        raise ReverseEngineeringError("attribution snapshots must share probe_digest")
    sets = [set(item.feature_ids) for item in ordered]
    jaccards: list[float] = []
    for left, right in combinations(sets, 2):
        union = left | right
        jaccards.append(len(left & right) / len(union))
    all_features = set().union(*sets)
    universal = set.intersection(*sets)
    threshold = len(sets) / 2.0
    majority = {
        feature
        for feature in all_features
        if sum(feature in values for values in sets) > threshold
    }
    payload = {
        "probe_digest": ordered[0].probe_digest,
        "snapshots": [
            {"snapshot_id": item.snapshot_id, "feature_ids": list(item.feature_ids)}
            for item in ordered
        ],
    }
    return AttributionStabilityReport(
        snapshot_count=len(ordered),
        unique_feature_count=len(all_features),
        mean_pairwise_jaccard=sum(jaccards) / len(jaccards),
        min_pairwise_jaccard=min(jaccards),
        universal_feature_count=len(universal),
        majority_feature_count=len(majority),
        digest=stable_digest(payload),
    )

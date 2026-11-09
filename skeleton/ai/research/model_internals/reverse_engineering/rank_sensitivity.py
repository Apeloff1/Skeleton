"""Rank-sensitivity analysis for ordered attribution or feature lists."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class RankedFeatureList:
    list_id: str
    probe_digest: str
    feature_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.list_id:
            raise ReverseEngineeringError("ranked feature list requires identity")
        if not is_sha256_digest(self.probe_digest):
            raise ReverseEngineeringError("probe_digest must be a sha256 hex digest")
        if not self.feature_ids:
            raise ReverseEngineeringError("ranked feature list must be non-empty")
        if len(self.feature_ids) != len(set(self.feature_ids)):
            raise ReverseEngineeringError("ranked feature ids must be unique")


@dataclass(frozen=True)
class RankSensitivityPoint:
    k: int
    mean_pairwise_jaccard: float


@dataclass(frozen=True)
class RankSensitivityReport:
    list_count: int
    max_rank: int
    points: tuple[RankSensitivityPoint, ...]
    stable_prefix_length: int
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "list_count": self.list_count,
            "max_rank": self.max_rank,
            "points": [
                {"k": point.k, "mean_pairwise_jaccard": point.mean_pairwise_jaccard}
                for point in self.points
            ],
            "stable_prefix_length": self.stable_prefix_length,
            "digest": self.digest,
        }


def analyze_rank_sensitivity(
    lists: Sequence[RankedFeatureList],
    *,
    stable_threshold: float = 0.5,
) -> RankSensitivityReport:
    if len(lists) < 2:
        raise ReverseEngineeringError("rank sensitivity requires at least two lists")
    probe_digests = {item.probe_digest for item in lists}
    if len(probe_digests) != 1:
        raise ReverseEngineeringError("ranked lists must share probe_digest")
    if not 0.0 <= stable_threshold <= 1.0:
        raise ReverseEngineeringError("stable_threshold must be within [0, 1]")

    max_rank = min(len(item.feature_ids) for item in lists)
    points: list[RankSensitivityPoint] = []
    for k in range(1, max_rank + 1):
        prefix_sets = [set(item.feature_ids[:k]) for item in lists]
        jaccards: list[float] = []
        for i in range(len(prefix_sets)):
            for j in range(i + 1, len(prefix_sets)):
                left = prefix_sets[i]
                right = prefix_sets[j]
                jaccards.append(len(left & right) / len(left | right))
        points.append(
            RankSensitivityPoint(
                k=k,
                mean_pairwise_jaccard=sum(jaccards) / len(jaccards),
            )
        )
    stable_prefix = 0
    for point in points:
        if point.mean_pairwise_jaccard >= stable_threshold:
            stable_prefix = point.k
        else:
            break
    payload = {
        "probe_digest": next(iter(probe_digests)),
        "stable_threshold": stable_threshold,
        "lists": [
            {"list_id": item.list_id, "feature_ids": list(item.feature_ids)}
            for item in sorted(lists, key=lambda value: value.list_id)
        ],
    }
    return RankSensitivityReport(
        list_count=len(lists),
        max_rank=max_rank,
        points=tuple(points),
        stable_prefix_length=stable_prefix,
        digest=stable_digest(payload),
    )

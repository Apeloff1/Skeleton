"""Composite distance between normalized model/research signatures."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt
from typing import Any, Mapping

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class SignatureDistanceReport:
    feature_count: int
    euclidean_distance: float
    mean_absolute_distance: float
    max_absolute_distance: float
    closest: bool
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "feature_count": self.feature_count,
            "euclidean_distance": self.euclidean_distance,
            "mean_absolute_distance": self.mean_absolute_distance,
            "max_absolute_distance": self.max_absolute_distance,
            "closest": self.closest,
            "digest": self.digest,
        }


def analyze_signature_distance(
    left: Mapping[str, float],
    right: Mapping[str, float],
    *,
    closeness_threshold: float = 0.1,
) -> SignatureDistanceReport:
    if set(left) != set(right) or not left:
        raise ReverseEngineeringError("signature feature sets must be non-empty and identical")
    if not isfinite(closeness_threshold) or closeness_threshold < 0.0:
        raise ReverseEngineeringError("closeness_threshold must be finite and non-negative")
    differences: list[float] = []
    for key in sorted(left):
        a = float(left[key])
        b = float(right[key])
        if not isfinite(a) or not isfinite(b):
            raise ReverseEngineeringError("signature values must be finite")
        differences.append(a - b)
    absolute = [abs(value) for value in differences]
    euclidean = sqrt(sum(value * value for value in differences))
    mean_absolute = sum(absolute) / len(absolute)
    payload = {
        "left": {key: float(left[key]) for key in sorted(left)},
        "right": {key: float(right[key]) for key in sorted(right)},
        "closeness_threshold": closeness_threshold,
    }
    return SignatureDistanceReport(
        feature_count=len(differences),
        euclidean_distance=euclidean,
        mean_absolute_distance=mean_absolute,
        max_absolute_distance=max(absolute),
        closest=mean_absolute <= closeness_threshold,
        digest=stable_digest(payload),
    )

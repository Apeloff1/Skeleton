"""Version-to-version drift for normalized model signatures."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt
from typing import Any, Mapping, Sequence

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class VersionSignature:
    version_id: str
    ordinal: int
    features: tuple[tuple[str, float], ...]

    def __post_init__(self) -> None:
        if not self.version_id:
            raise ReverseEngineeringError("version signature requires identity")
        if self.ordinal < 0:
            raise ReverseEngineeringError("version ordinal must be non-negative")
        names = [name for name, _ in self.features]
        if not names or len(names) != len(set(names)):
            raise ReverseEngineeringError("version signature features must be non-empty and unique")
        if any(not name or not isfinite(value) for name, value in self.features):
            raise ReverseEngineeringError("version signature values must be finite")


@dataclass(frozen=True)
class VersionDriftStep:
    from_version: str
    to_version: str
    euclidean_distance: float
    mean_absolute_distance: float
    max_absolute_distance: float


@dataclass(frozen=True)
class VersionDriftReport:
    version_count: int
    feature_count: int
    steps: tuple[VersionDriftStep, ...]
    cumulative_euclidean_distance: float
    maximum_step_distance: float
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "version_count": self.version_count,
            "feature_count": self.feature_count,
            "steps": [
                {
                    "from_version": step.from_version,
                    "to_version": step.to_version,
                    "euclidean_distance": step.euclidean_distance,
                    "mean_absolute_distance": step.mean_absolute_distance,
                    "max_absolute_distance": step.max_absolute_distance,
                }
                for step in self.steps
            ],
            "cumulative_euclidean_distance": self.cumulative_euclidean_distance,
            "maximum_step_distance": self.maximum_step_distance,
            "digest": self.digest,
        }


def analyze_version_drift(
    signatures: Sequence[VersionSignature],
) -> VersionDriftReport:
    if len(signatures) < 2:
        raise ReverseEngineeringError("version drift requires at least two signatures")
    ordered = sorted(signatures, key=lambda item: (item.ordinal, item.version_id))
    ordinals = [item.ordinal for item in ordered]
    if len(ordinals) != len(set(ordinals)):
        raise ReverseEngineeringError("version ordinals must be unique")
    feature_names = tuple(name for name, _ in sorted(ordered[0].features))
    mappings: list[Mapping[str, float]] = []
    for signature in ordered:
        mapping = dict(signature.features)
        if tuple(sorted(mapping)) != feature_names:
            raise ReverseEngineeringError("version signatures must share feature sets")
        mappings.append(mapping)

    steps: list[VersionDriftStep] = []
    for left_sig, right_sig, left, right in zip(ordered, ordered[1:], mappings, mappings[1:]):
        differences = [right[name] - left[name] for name in feature_names]
        absolute = [abs(value) for value in differences]
        steps.append(
            VersionDriftStep(
                from_version=left_sig.version_id,
                to_version=right_sig.version_id,
                euclidean_distance=sqrt(sum(value * value for value in differences)),
                mean_absolute_distance=sum(absolute) / len(absolute),
                max_absolute_distance=max(absolute),
            )
        )
    payload = {
        "signatures": [
            {
                "version_id": item.version_id,
                "ordinal": item.ordinal,
                "features": [[name, value] for name, value in sorted(item.features)],
            }
            for item in ordered
        ]
    }
    return VersionDriftReport(
        version_count=len(ordered),
        feature_count=len(feature_names),
        steps=tuple(steps),
        cumulative_euclidean_distance=sum(step.euclidean_distance for step in steps),
        maximum_step_distance=max(step.euclidean_distance for step in steps),
        digest=stable_digest(payload),
    )

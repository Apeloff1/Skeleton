"""Effect transportability between source and target environments."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class TransportObservation:
    observation_id: str
    probe_digest: str
    environment: str
    role: str
    effect: float

    def __post_init__(self) -> None:
        if not self.observation_id or not self.environment:
            raise ReverseEngineeringError("transport observation identity is required")
        if self.role not in {"source", "target"}:
            raise ReverseEngineeringError("transport role must be source or target")
        if not is_sha256_digest(self.probe_digest):
            raise ReverseEngineeringError("probe_digest must be sha256 hex")
        if not isfinite(self.effect):
            raise ReverseEngineeringError("transport effect must be finite")


@dataclass(frozen=True)
class TransportabilityReport:
    source_environment_count: int
    target_environment_count: int
    source_mean_effect: float
    target_mean_effect: float
    absolute_transport_gap: float
    relative_transport_gap: float | None
    sign_preserved: bool
    transportable: bool
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_environment_count": self.source_environment_count,
            "target_environment_count": self.target_environment_count,
            "source_mean_effect": self.source_mean_effect,
            "target_mean_effect": self.target_mean_effect,
            "absolute_transport_gap": self.absolute_transport_gap,
            "relative_transport_gap": self.relative_transport_gap,
            "sign_preserved": self.sign_preserved,
            "transportable": self.transportable,
            "digest": self.digest,
        }


def analyze_transportability(
    observations: Sequence[TransportObservation],
    *,
    absolute_gap_tolerance: float = 0.2,
) -> TransportabilityReport:
    if not observations:
        raise ReverseEngineeringError("transportability requires observations")
    if not isfinite(absolute_gap_tolerance) or absolute_gap_tolerance < 0.0:
        raise ReverseEngineeringError("absolute_gap_tolerance must be finite and non-negative")
    digests = {item.probe_digest for item in observations}
    if len(digests) != 1:
        raise ReverseEngineeringError("transport observations must share probe_digest")
    source = [item for item in observations if item.role == "source"]
    target = [item for item in observations if item.role == "target"]
    if not source or not target:
        raise ReverseEngineeringError("transportability requires source and target observations")
    source_mean = sum(item.effect for item in source) / len(source)
    target_mean = sum(item.effect for item in target) / len(target)
    gap = abs(target_mean - source_mean)
    relative = gap / abs(source_mean) if source_mean != 0.0 else None
    sign_preserved = (
        source_mean == 0.0 and target_mean == 0.0
        or (source_mean > 0.0 and target_mean > 0.0)
        or (source_mean < 0.0 and target_mean < 0.0)
    )
    payload = {
        "probe_digest": next(iter(digests)),
        "absolute_gap_tolerance": absolute_gap_tolerance,
        "observations": [
            {
                "observation_id": item.observation_id,
                "environment": item.environment,
                "role": item.role,
                "effect": item.effect,
            }
            for item in sorted(observations, key=lambda value: value.observation_id)
        ],
    }
    return TransportabilityReport(
        source_environment_count=len({item.environment for item in source}),
        target_environment_count=len({item.environment for item in target}),
        source_mean_effect=source_mean,
        target_mean_effect=target_mean,
        absolute_transport_gap=gap,
        relative_transport_gap=relative,
        sign_preserved=sign_preserved,
        transportable=sign_preserved and gap <= absolute_gap_tolerance,
        digest=stable_digest(payload),
    )

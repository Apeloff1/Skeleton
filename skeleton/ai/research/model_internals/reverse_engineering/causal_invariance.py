"""Causal-effect invariance across environments or experimental contexts."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class EnvironmentEffect:
    observation_id: str
    probe_digest: str
    environment: str
    effect: float

    def __post_init__(self) -> None:
        if not self.observation_id or not self.environment:
            raise ReverseEngineeringError("environment effect identity is required")
        if not is_sha256_digest(self.probe_digest):
            raise ReverseEngineeringError("probe_digest must be sha256 hex")
        if not isfinite(self.effect):
            raise ReverseEngineeringError("environment effect must be finite")


@dataclass(frozen=True)
class CausalInvarianceReport:
    environment_count: int
    observation_count: int
    mean_effect_by_environment: tuple[tuple[str, float], ...]
    mean_effect: float
    max_environment_deviation: float
    sign_consistency: float
    invariant: bool
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "environment_count": self.environment_count,
            "observation_count": self.observation_count,
            "mean_effect_by_environment": [list(item) for item in self.mean_effect_by_environment],
            "mean_effect": self.mean_effect,
            "max_environment_deviation": self.max_environment_deviation,
            "sign_consistency": self.sign_consistency,
            "invariant": self.invariant,
            "digest": self.digest,
        }


def analyze_causal_invariance(
    effects: Sequence[EnvironmentEffect],
    *,
    max_deviation_tolerance: float = 0.2,
) -> CausalInvarianceReport:
    if not effects:
        raise ReverseEngineeringError("causal invariance requires effects")
    if not isfinite(max_deviation_tolerance) or max_deviation_tolerance < 0.0:
        raise ReverseEngineeringError("max_deviation_tolerance must be finite and non-negative")
    probe_digests = {item.probe_digest for item in effects}
    if len(probe_digests) != 1:
        raise ReverseEngineeringError("causal invariance effects must share probe_digest")

    grouped: dict[str, list[float]] = {}
    for item in effects:
        grouped.setdefault(item.environment, []).append(item.effect)
    means = tuple(
        sorted((environment, sum(values) / len(values)) for environment, values in grouped.items())
    )
    mean_effect = sum(value for _, value in means) / len(means)
    deviations = [abs(value - mean_effect) for _, value in means]
    signs = {0 if value == 0.0 else (1 if value > 0.0 else -1) for _, value in means}
    sign_consistency = 1.0 if len(signs) == 1 else 0.0
    max_deviation = max(deviations)
    payload = {
        "probe_digest": next(iter(probe_digests)),
        "max_deviation_tolerance": max_deviation_tolerance,
        "effects": [
            {
                "observation_id": item.observation_id,
                "environment": item.environment,
                "effect": item.effect,
            }
            for item in sorted(effects, key=lambda value: value.observation_id)
        ],
    }
    return CausalInvarianceReport(
        environment_count=len(grouped),
        observation_count=len(effects),
        mean_effect_by_environment=means,
        mean_effect=mean_effect,
        max_environment_deviation=max_deviation,
        sign_consistency=sign_consistency,
        invariant=(max_deviation <= max_deviation_tolerance and sign_consistency == 1.0),
        digest=stable_digest(payload),
    )

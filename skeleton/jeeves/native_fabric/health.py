"""Host-side health and readiness levels with explicit unknown telemetry.

A synthetic metric or missing device sensor cannot become a pass. The policy
holds unverified GPU/CPU/RAM pressure, rights, model identity, and current
native activation independently. No health estimate substitutes the existing
source-bound install and canonical SQLite gates.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from statistics import median
from typing import Mapping, Sequence

from .contracts import ContractHold, finite, exact_integer, identifier, digest


@dataclass(frozen=True, slots=True)
class HealthSignal:
    signal_id: str
    observed: float | None
    lower: float | None
    upper: float | None
    sample_age_ms: int | None = None
    confidence: float = 1.0
    required: bool = True

    def __post_init__(self):
        identifier(self.signal_id, "health signal")
        for value in (self.observed, self.lower, self.upper):
            if value is not None:
                finite(value, minimum=-1e12, maximum=1e12)
        if self.sample_age_ms is not None:
            exact_integer(self.sample_age_ms, maximum=86400000)
        finite(self.confidence, minimum=0, maximum=1)
        if type(self.required) is not bool:
            raise ContractHold("health requirement must be strict boolean")
        if (self.lower is None and self.upper is None):
            raise ContractHold("health interval needs a bound")
        if self.lower is not None and self.upper is not None and self.lower > self.upper:
            raise ContractHold("health interval inverted")

    def status(self, *, maximum_age_ms: int = 15000) -> str:
        exact_integer(maximum_age_ms, minimum=1, maximum=86400000)
        if self.observed is None or self.sample_age_ms is None:
            return "unknown"
        if self.sample_age_ms > maximum_age_ms or self.confidence < 0.8:
            return "stale"
        if (self.lower is not None and self.observed < self.lower
            or self.upper is not None and self.observed > self.upper):
            return "out_of_range"
        return "healthy"


@dataclass(frozen=True, slots=True)
class HealthAssessment:
    readiness: str
    healthy: tuple[str, ...]
    missing: tuple[str, ...]
    degraded: tuple[str, ...]
    optional_missing: tuple[str, ...]
    sample_count: int

    @property
    def can_activate(self) -> bool:
        return self.readiness == "eligible_for_further_admission"

    def to_record(self):
        return {
            "schema": "jeeves.fabric.health_assessment.v1",
            "readiness": self.readiness,
            "healthy": list(self.healthy), "missing": list(self.missing),
            "degraded": list(self.degraded),
            "optional_missing": list(self.optional_missing),
            "sample_count": self.sample_count,
            "native_model_proven": False,
            "device_qualified": False,
            "release_certified": False,
        }


def assess_health(
    signals: Sequence[HealthSignal], *,
    expected_ids: Sequence[str],
    maximum_age_ms: int = 15000,
) -> HealthAssessment:
    exact_integer(maximum_age_ms, minimum=1, maximum=86400000)
    if type(signals) not in (tuple, list) or len(signals) > 512:
        raise ContractHold("bounded typed signals required")
    if type(expected_ids) not in (tuple, list) or not 1 <= len(expected_ids) <= 512:
        raise ContractHold("explicit expected signal inventory required")
    expected = set(identifier(i) for i in expected_ids)
    if len(expected) != len(expected_ids):
        raise ContractHold("duplicate expected health signal")
    observed = {}
    for signal in signals:
        if not isinstance(signal, HealthSignal):
            raise ContractHold("unexpected health signal type")
        if signal.signal_id in observed or signal.signal_id not in expected:
            raise ContractHold("duplicate or unexpected telemetry")
        observed[signal.signal_id] = signal
    healthy, missing, degraded, optional_missing = [], [], [], []
    for name in sorted(expected):
        signal = observed.get(name)
        if signal is None:
            missing.append(name)
            continue
        result = signal.status(maximum_age_ms=maximum_age_ms)
        if result == "healthy":
            healthy.append(name)
        elif not signal.required and result in ("unknown", "stale"):
            optional_missing.append(name)
        else:
            degraded.append(name)
    state = (
        "held_missing_telemetry" if missing else
        "held_degraded_telemetry" if degraded else
        "eligible_for_further_admission"
    )
    return HealthAssessment(
        readiness=state, healthy=tuple(healthy),
        missing=tuple(missing), degraded=tuple(degraded),
        optional_missing=tuple(optional_missing),
        sample_count=len(signals),
    )


def quantiles(values: Sequence[float], *,
              percentiles: Sequence[float] = (0.5, 0.9, 0.95, 0.99)) -> dict[str, float]:
    if type(values) not in (tuple, list) or not 1 <= len(values) <= 100000:
        raise ContractHold("bounded nonempty real observation series required")
    if type(percentiles) not in (tuple, list) or not 1 <= len(percentiles) <= 32:
        raise ContractHold("bounded percentile specification required")
    checked = sorted(finite(value, minimum=0, maximum=1e12) for value in values)
    result = {}
    for p in percentiles:
        finite(p, minimum=0, maximum=1)
        position = p * (len(checked) - 1)
        low, high = math.floor(position), math.ceil(position)
        fraction = position - low
        estimate = checked[low] * (1 - fraction) + checked[high] * fraction
        result[f"p{int(p * 10000):04d}"] = estimate
    return result


def sliding_rate(
    timestamps_ms: Sequence[int], *, window_ms: int,
    observed_at_ms: int,
) -> float:
    exact_integer(window_ms, minimum=1, maximum=86400000)
    exact_integer(observed_at_ms, maximum=10**15)
    if type(timestamps_ms) not in (tuple, list) or len(timestamps_ms) > 100000:
        raise ContractHold("unbounded throughput sample")
    for value in timestamps_ms:
        exact_integer(value, maximum=10**15)
        if value > observed_at_ms:
            raise ContractHold("future timestamp in throughput sample")
    start = observed_at_ms - window_ms
    return 1000 * sum(start <= item <= observed_at_ms
                      for item in timestamps_ms) / window_ms


__all__ = ["HealthSignal", "HealthAssessment",
           "assess_health", "quantiles", "sliding_rate"]

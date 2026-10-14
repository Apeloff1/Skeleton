"""Prefill/decode scaling signatures from controlled performance observations."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, log
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class LatencyObservation:
    observation_id: str
    phase: str
    input_units: int
    output_units: int
    elapsed_ms: float
    batch_size: int = 1

    def __post_init__(self) -> None:
        if not self.observation_id or not self.phase:
            raise ReverseEngineeringError("latency observation identity is required")
        if self.input_units < 0 or self.output_units < 0 or self.batch_size <= 0:
            raise ReverseEngineeringError("latency unit counts must be non-negative and batch positive")
        if not isfinite(self.elapsed_ms) or self.elapsed_ms <= 0.0:
            raise ReverseEngineeringError("elapsed_ms must be finite and positive")

    @property
    def scale_units(self) -> int:
        if self.phase == "prefill":
            return self.input_units
        if self.phase == "decode":
            return self.output_units
        return self.input_units + self.output_units


@dataclass(frozen=True)
class LatencyScalingReport:
    phase: str
    observation_count: int
    min_scale_units: int
    max_scale_units: int
    mean_ms_per_scale_unit: float
    log_log_exponent: float | None
    r_squared: float | None
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "observation_count": self.observation_count,
            "min_scale_units": self.min_scale_units,
            "max_scale_units": self.max_scale_units,
            "mean_ms_per_scale_unit": self.mean_ms_per_scale_unit,
            "log_log_exponent": self.log_log_exponent,
            "r_squared": self.r_squared,
            "digest": self.digest,
        }


def _fit_log_log(xs: Sequence[float], ys: Sequence[float]) -> tuple[float | None, float | None]:
    if len(xs) < 2 or len(set(xs)) < 2:
        return None, None
    lx = [log(value) for value in xs]
    ly = [log(value) for value in ys]
    mean_x = sum(lx) / len(lx)
    mean_y = sum(ly) / len(ly)
    ss_x = sum((value - mean_x) ** 2 for value in lx)
    if ss_x == 0.0:
        return None, None
    covariance = sum((x - mean_x) * (y - mean_y) for x, y in zip(lx, ly))
    slope = covariance / ss_x
    intercept = mean_y - slope * mean_x
    predicted = [intercept + slope * value for value in lx]
    ss_res = sum((actual - pred) ** 2 for actual, pred in zip(ly, predicted))
    ss_tot = sum((actual - mean_y) ** 2 for actual in ly)
    r_squared = 1.0 if ss_tot == 0.0 and ss_res == 0.0 else (None if ss_tot == 0.0 else 1.0 - ss_res / ss_tot)
    return slope, r_squared


def analyze_latency_scaling(
    observations: Sequence[LatencyObservation],
) -> tuple[LatencyScalingReport, ...]:
    if not observations:
        raise ReverseEngineeringError("latency scaling requires observations")
    grouped: dict[str, list[LatencyObservation]] = {}
    for item in observations:
        grouped.setdefault(item.phase, []).append(item)

    reports: list[LatencyScalingReport] = []
    for phase, items in sorted(grouped.items()):
        ordered = sorted(items, key=lambda item: (item.scale_units, item.observation_id))
        positive = [item for item in ordered if item.scale_units > 0]
        if not positive:
            raise ReverseEngineeringError(f"phase {phase!r} requires positive scale units")
        xs = [float(item.scale_units) for item in positive]
        ys = [item.elapsed_ms / item.batch_size for item in positive]
        exponent, r_squared = _fit_log_log(xs, ys)
        payload = {
            "phase": phase,
            "observations": [
                {
                    "observation_id": item.observation_id,
                    "input_units": item.input_units,
                    "output_units": item.output_units,
                    "elapsed_ms": item.elapsed_ms,
                    "batch_size": item.batch_size,
                }
                for item in ordered
            ],
        }
        reports.append(
            LatencyScalingReport(
                phase=phase,
                observation_count=len(ordered),
                min_scale_units=min(item.scale_units for item in positive),
                max_scale_units=max(item.scale_units for item in positive),
                mean_ms_per_scale_unit=sum(
                    (item.elapsed_ms / item.batch_size) / item.scale_units for item in positive
                ) / len(positive),
                log_log_exponent=exponent,
                r_squared=r_squared,
                digest=stable_digest(payload),
            )
        )
    return tuple(reports)

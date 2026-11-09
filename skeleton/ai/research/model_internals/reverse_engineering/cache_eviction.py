"""Cache-retention and eviction characterization for authorized runtimes."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class CacheTrial:
    trial_id: str
    capacity_units: int
    inserted_units: int
    retained_units: int
    hit_rate: float
    condition: str = "default"

    def __post_init__(self) -> None:
        if not self.trial_id or not self.condition:
            raise ReverseEngineeringError("cache trial identity is required")
        if self.capacity_units <= 0 or self.inserted_units < 0 or self.retained_units < 0:
            raise ReverseEngineeringError("cache units must be non-negative and capacity positive")
        if self.retained_units > self.inserted_units:
            raise ReverseEngineeringError("retained_units cannot exceed inserted_units")
        if not isfinite(self.hit_rate) or not 0.0 <= self.hit_rate <= 1.0:
            raise ReverseEngineeringError("hit_rate must be finite and within [0, 1]")


@dataclass(frozen=True)
class CacheEvictionReport:
    condition: str
    trial_count: int
    first_over_capacity_units: int | None
    first_retention_loss_units: int | None
    mean_hit_rate: float
    mean_retention_ratio: float
    monotonicity_violations: int
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "condition": self.condition,
            "trial_count": self.trial_count,
            "first_over_capacity_units": self.first_over_capacity_units,
            "first_retention_loss_units": self.first_retention_loss_units,
            "mean_hit_rate": self.mean_hit_rate,
            "mean_retention_ratio": self.mean_retention_ratio,
            "monotonicity_violations": self.monotonicity_violations,
            "digest": self.digest,
        }


def analyze_cache_eviction(trials: Sequence[CacheTrial]) -> tuple[CacheEvictionReport, ...]:
    if not trials:
        raise ReverseEngineeringError("cache eviction analysis requires trials")
    grouped: dict[str, list[CacheTrial]] = {}
    for trial in trials:
        grouped.setdefault(trial.condition, []).append(trial)

    reports: list[CacheEvictionReport] = []
    for condition, items in sorted(grouped.items()):
        ordered = sorted(items, key=lambda item: (item.inserted_units, item.trial_id))
        retention_ratios = [
            (item.retained_units / item.inserted_units if item.inserted_units else 1.0)
            for item in ordered
        ]
        violations = 0
        previous: float | None = None
        for ratio in retention_ratios:
            if previous is not None and ratio > previous + 1e-12:
                violations += 1
            previous = ratio
        over_capacity = [
            item.inserted_units for item in ordered if item.inserted_units > item.capacity_units
        ]
        retention_loss = [
            item.inserted_units for item in ordered if item.retained_units < item.inserted_units
        ]
        payload = {
            "condition": condition,
            "trials": [
                {
                    "trial_id": item.trial_id,
                    "capacity_units": item.capacity_units,
                    "inserted_units": item.inserted_units,
                    "retained_units": item.retained_units,
                    "hit_rate": item.hit_rate,
                }
                for item in ordered
            ],
        }
        reports.append(
            CacheEvictionReport(
                condition=condition,
                trial_count=len(ordered),
                first_over_capacity_units=min(over_capacity) if over_capacity else None,
                first_retention_loss_units=min(retention_loss) if retention_loss else None,
                mean_hit_rate=sum(item.hit_rate for item in ordered) / len(ordered),
                mean_retention_ratio=sum(retention_ratios) / len(retention_ratios),
                monotonicity_violations=violations,
                digest=stable_digest(payload),
            )
        )
    return tuple(reports)

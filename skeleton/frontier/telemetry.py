"""Small dependency-free telemetry primitives for runtime observability."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Mapping


@dataclass(frozen=True, slots=True)
class MetricSample:
    name: str
    value: float
    observed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    tags: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("metric name must not be empty")
        if self.observed_at.tzinfo is None:
            raise ValueError("observed_at must be timezone-aware")


@dataclass(slots=True)
class TelemetryBuffer:
    samples: list[MetricSample] = field(default_factory=list)

    def record(self, sample: MetricSample) -> None:
        self.samples.append(sample)

    def values(self, name: str) -> list[float]:
        return [sample.value for sample in self.samples if sample.name == name]

    def latest(self, name: str) -> MetricSample | None:
        matches = [sample for sample in self.samples if sample.name == name]
        return matches[-1] if matches else None

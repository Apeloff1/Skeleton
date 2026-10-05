"""Bounded, dependency-free telemetry for runtime observability."""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock
from types import MappingProxyType

from skeleton.frontier.execution import positive_int


@dataclass(frozen=True, slots=True)
class MetricSample:
    name: str
    value: float
    observed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    tags: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip() or len(self.name) > 128:
            raise ValueError("metric name must contain 1 to 128 characters")
        if (
            isinstance(self.value, bool)
            or not isinstance(self.value, (int, float))
            or not math.isfinite(self.value)
        ):
            raise ValueError("metric value must be finite")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        tags = dict(self.tags)
        if len(tags) > 16 or any(
            not isinstance(k, str) or not isinstance(v, str) or len(k) > 128 or len(v) > 256
            for k, v in tags.items()
        ):
            raise ValueError("metric tags exceed the string label limits")
        object.__setattr__(self, "tags", MappingProxyType(tags))


class TelemetryBuffer:
    def __init__(self, samples: Iterable[MetricSample] = (), *, capacity: int = 4096) -> None:
        self.capacity = positive_int("capacity", capacity)
        self._samples: deque[MetricSample] = deque(maxlen=capacity)
        self._lock = Lock()
        self.dropped = 0
        for sample in samples:
            self.record(sample)

    @property
    def samples(self) -> tuple[MetricSample, ...]:
        with self._lock:
            return tuple(self._samples)

    def record(self, sample: MetricSample) -> None:
        if not isinstance(sample, MetricSample):
            raise TypeError("sample must be MetricSample")
        with self._lock:
            if len(self._samples) == self.capacity:
                self.dropped += 1
            self._samples.append(sample)

    def values(self, name: str) -> list[float]:
        return [sample.value for sample in self.samples if sample.name == name]

    def latest(self, name: str) -> MetricSample | None:
        return next((sample for sample in reversed(self.samples) if sample.name == name), None)

    def summary(self, name: str) -> dict[str, float | int | None]:
        values = sorted(self.values(name))
        if not values:
            return {"count": 0, "min": None, "max": None, "mean": None, "p50": None, "p95": None}

        def percentile(fraction: float) -> float:
            position = fraction * (len(values) - 1)
            lower = int(position)
            upper = min(lower + 1, len(values) - 1)
            return values[lower] + (values[upper] - values[lower]) * (position - lower)

        return {
            "count": len(values),
            "min": values[0],
            "max": values[-1],
            "mean": sum(values) / len(values),
            "p50": percentile(0.5),
            "p95": percentile(0.95),
        }

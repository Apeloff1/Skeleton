"""Small streaming metrics used by evaluation and control loops."""
from __future__ import annotations

from dataclasses import dataclass
from math import sqrt


@dataclass(slots=True)
class RunningStats:
    count: int = 0
    mean: float = 0.0
    m2: float = 0.0

    def push(self, value: float) -> None:
        if not isinstance(value, (int, float)):
            raise TypeError("value must be numeric")
        self.count += 1
        delta = value - self.mean
        self.mean += delta / self.count
        self.m2 += delta * (value - self.mean)

    @property
    def variance(self) -> float:
        return self.m2 / (self.count - 1) if self.count > 1 else 0.0

    @property
    def standard_deviation(self) -> float:
        return sqrt(self.variance)

    def snapshot(self) -> dict[str, float | int]:
        return {"count": self.count, "mean": self.mean, "variance": self.variance}


@dataclass(slots=True)
class QualityWindow:
    """Tracks quality, latency, and failure rate without retaining samples."""

    quality: RunningStats = RunningStats()
    latency_ms: RunningStats = RunningStats()
    failures: int = 0

    def record(self, quality: float, latency_ms: float, *, failed: bool = False) -> None:
        self.quality.push(quality)
        self.latency_ms.push(latency_ms)
        self.failures += int(failed)

    @property
    def failure_rate(self) -> float:
        return self.failures / self.quality.count if self.quality.count else 0.0

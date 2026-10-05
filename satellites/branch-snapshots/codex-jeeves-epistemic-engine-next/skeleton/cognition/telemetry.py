"""Low-overhead counters, gauges, histograms and spans for cognition."""
from __future__ import annotations
from dataclasses import dataclass, field
from time import monotonic
from typing import Any

@dataclass(slots=True)
class MetricRegistry:
    counters: dict[str, int] = field(default_factory=dict)
    gauges: dict[str, float] = field(default_factory=dict)
    samples: dict[str, list[float]] = field(default_factory=dict)

    def inc(self, name: str, amount: int = 1) -> int:
        self.counters[name] = self.counters.get(name, 0) + int(amount)
        return self.counters[name]

    def set(self, name: str, value: float) -> None:
        self.gauges[name] = float(value)

    def observe(self, name: str, value: float, *, limit: int = 1024) -> None:
        bucket = self.samples.setdefault(name, [])
        bucket.append(float(value))
        if len(bucket) > max(1, limit):
            del bucket[: len(bucket) - limit]

    def snapshot(self) -> dict[str, Any]:
        return {
            "counters": dict(sorted(self.counters.items())),
            "gauges": dict(sorted(self.gauges.items())),
            "samples": {k: tuple(v) for k, v in sorted(self.samples.items())},
        }

@dataclass(frozen=True, slots=True)
class Span:
    name: str
    duration_ms: float
    attributes: tuple[tuple[str, str], ...] = ()

class SpanTimer:
    def __init__(self, registry: MetricRegistry, name: str, **attributes: object) -> None:
        self.registry, self.name = registry, name
        self.attributes = tuple(sorted((str(k), str(v)) for k, v in attributes.items()))
        self.started = monotonic()

    def finish(self) -> Span:
        duration = (monotonic() - self.started) * 1000.0
        self.registry.observe(f"latency_ms.{self.name}", duration)
        return Span(self.name, duration, self.attributes)

__all__ = ["MetricRegistry", "Span", "SpanTimer"]

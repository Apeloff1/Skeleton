"""Resource-pressure policy; unknown readings are not interpreted as healthy."""
from __future__ import annotations

from dataclasses import dataclass
import math

from .errors import deny
from .contracts import strict_integer


@dataclass(frozen=True, slots=True)
class Pressure:
    memory_ratio: float
    cpu_ratio: float
    queue_ratio: float
    sampled_mono_ms: int

    def __post_init__(self) -> None:
        for name in ("memory_ratio", "cpu_ratio", "queue_ratio"):
            value = getattr(self, name)
            if type(value) not in (float, int) or not math.isfinite(value) or not 0 <= value <= 1:
                deny("pressure-unknown")
        strict_integer(self.sampled_mono_ms, minimum=0, maximum=2**63 - 1, field="sample-time")


@dataclass(frozen=True, slots=True)
class PressurePolicy:
    degraded_at: float = 0.7
    blocked_at: float = 0.9
    maximum_age_ms: int = 1000

    def __post_init__(self) -> None:
        if not (type(self.degraded_at) is float and type(self.blocked_at) is float):
            deny("pressure-threshold")
        if not (0 < self.degraded_at < self.blocked_at <= 1):
            deny("pressure-threshold")
        strict_integer(self.maximum_age_ms, minimum=1, maximum=60000, field="sample-age")

    def decide(self, sample: Pressure, now_ms: int) -> str:
        strict_integer(now_ms, minimum=0, maximum=2**63 - 1, field="clock")
        if sample.sampled_mono_ms > now_ms or now_ms - sample.sampled_mono_ms > self.maximum_age_ms:
            deny("pressure-stale")
        value = max(sample.memory_ratio, sample.cpu_ratio, sample.queue_ratio)
        if value >= self.blocked_at:
            deny("pressure-blocked")
        if value >= self.degraded_at:
            return "degraded"
        return "healthy"

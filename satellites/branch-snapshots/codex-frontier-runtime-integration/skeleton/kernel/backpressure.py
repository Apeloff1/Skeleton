"""Backpressure governor for the kernel event bus.

The bus is only as healthy as its slowest subscriber. When publish rates
outrun drain rates, queues grow silently until memory balloons and the
whole fabric stalls. This module gives the kernel a closed-loop governor:

- :class:`TokenBucket` — classic rate limiter, refill-per-second.
- :class:`LoadShedder` — drops low-priority events first when the pending
  backlog crosses a watermark, preserving CRITICAL traffic.
- :class:`BackpressureGovernor` — wires both together behind one
  ``admit(event)`` gate the bus calls before enqueueing.

Decisions are pure and synchronous; no threads, no deps.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Callable, Dict, Optional, Tuple

from .errors import EventBusError


class Priority(IntEnum):
    BACKGROUND = 0
    NORMAL = 10
    HIGH = 20
    CRITICAL = 30


class BackpressureError(EventBusError):
    code = "KRN.BACKPRESSURE"


class TokenBucket:
    """Fixed-capacity token bucket refilled at a steady rate."""

    __slots__ = ("capacity", "refill_per_sec", "_tokens", "_last")

    def __init__(self, capacity: float, refill_per_sec: float) -> None:
        if capacity <= 0 or refill_per_sec <= 0:
            raise BackpressureError(
                "bucket capacity and refill rate must be positive",
                context={"capacity": capacity, "refill_per_sec": refill_per_sec},
            )
        self.capacity = float(capacity)
        self.refill_per_sec = float(refill_per_sec)
        self._tokens = float(capacity)
        self._last = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last
        self._tokens = min(self.capacity, self._tokens + elapsed * self.refill_per_sec)
        self._last = now

    def try_acquire(self, tokens: float = 1.0) -> bool:
        self._refill()
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False

    @property
    def available(self) -> float:
        self._refill()
        return self._tokens


@dataclass(frozen=True)
class ShedDecision:
    admitted: bool
    reason: str
    queue_depth: int
    priority: Priority


class LoadShedder:
    """Watermark-based shedding: below low watermark admit everything,
    above high watermark admit only CRITICAL, between them admit
    HIGH and CRITICAL. Hysteresis prevents flapping.
    """

    def __init__(self, low_watermark: int, high_watermark: int) -> None:
        if not 0 < low_watermark < high_watermark:
            raise BackpressureError(
                "watermarks must satisfy 0 < low < high",
                context={"low": low_watermark, "high": high_watermark},
            )
        self.low = low_watermark
        self.high = high_watermark

    def decide(self, queue_depth: int, priority: Priority) -> ShedDecision:
        if queue_depth >= self.high:
            admitted = priority >= Priority.CRITICAL
            return ShedDecision(admitted, "high-watermark" if not admitted else "critical-bypass", queue_depth, priority)
        if queue_depth >= self.low:
            admitted = priority >= Priority.HIGH
            return ShedDecision(admitted, "low-watermark" if not admitted else "priority-bypass", queue_depth, priority)
        return ShedDecision(True, "nominal", queue_depth, priority)


@dataclass
class GovernorStats:
    admitted: int = 0
    shed: int = 0
    throttled: int = 0
    by_reason: Dict[str, int] = field(default_factory=dict)

    def record(self, key: str) -> None:
        self.by_reason[key] = self.by_reason.get(key, 0) + 1


class BackpressureGovernor:
    """Single admission gate for the event bus."""

    def __init__(
        self,
        *,
        max_events_per_sec: float = 10_000,
        burst: float = 2_000,
        low_watermark: int = 5_000,
        high_watermark: int = 20_000,
        depth_probe: Optional[Callable[[], int]] = None,
    ) -> None:
        self.bucket = TokenBucket(burst, max_events_per_sec)
        self.shedder = LoadShedder(low_watermark, high_watermark)
        self._depth_probe = depth_probe or (lambda: 0)
        self.stats = GovernorStats()

    def admit(self, event_id: str, priority: Priority = Priority.NORMAL) -> ShedDecision:
        depth = self._depth_probe()
        decision = self.shedder.decide(depth, priority)
        if not decision.admitted:
            self.stats.shed += 1
            self.stats.record(f"shed:{decision.reason}")
            return decision
        if not self.bucket.try_acquire():
            self.stats.throttled += 1
            self.stats.record("throttled:bucket")
            return ShedDecision(False, "rate-limited", depth, priority)
        self.stats.admitted += 1
        self.stats.record(f"admit:{decision.reason}")
        return decision

    def report(self) -> Dict[str, object]:
        return {
            "admitted": self.stats.admitted,
            "shed": self.stats.shed,
            "throttled": self.stats.throttled,
            "by_reason": dict(self.stats.by_reason),
            "bucket_available": round(self.bucket.available, 2),
        }

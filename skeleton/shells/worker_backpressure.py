"""Adaptive but deterministic backpressure decisions for shell workers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import threading
import time
from typing import Callable, Mapping


class BackpressureState(str, Enum):
    OPEN = "open"
    THROTTLED = "throttled"
    PAUSED = "paused"


@dataclass(frozen=True)
class BackpressurePolicy:
    queue_high_watermark: int = 500
    queue_critical_watermark: int = 2000
    inflight_high_watermark: int = 64
    inflight_critical_watermark: int = 256
    failure_ratio_high: float = 0.25
    failure_ratio_critical: float = 0.60
    latency_high_ms: float = 5_000.0
    latency_critical_ms: float = 30_000.0
    recovery_samples: int = 3
    throttle_factor: float = 0.5
    ewma_alpha: float = 0.25

    def __post_init__(self) -> None:
        if self.queue_high_watermark < 0 or self.queue_critical_watermark <= self.queue_high_watermark:
            raise ValueError("invalid queue watermarks")
        if self.inflight_high_watermark < 0 or self.inflight_critical_watermark <= self.inflight_high_watermark:
            raise ValueError("invalid inflight watermarks")
        if not 0 <= self.failure_ratio_high < self.failure_ratio_critical <= 1:
            raise ValueError("invalid failure-ratio thresholds")
        if self.latency_high_ms < 0 or self.latency_critical_ms <= self.latency_high_ms:
            raise ValueError("invalid latency thresholds")
        if self.recovery_samples <= 0:
            raise ValueError("recovery_samples must be positive")
        if not 0 < self.throttle_factor <= 1:
            raise ValueError("throttle_factor must be in (0, 1]")
        if not 0 < self.ewma_alpha <= 1:
            raise ValueError("ewma_alpha must be in (0, 1]")


@dataclass(frozen=True)
class BackpressureSample:
    queued: int
    claimed: int
    active_workers: int
    failed_workers: int
    recent_successes: int
    recent_failures: int
    latency_ms: float
    observed_at: float

    def __post_init__(self) -> None:
        values = (
            self.queued,
            self.claimed,
            self.active_workers,
            self.failed_workers,
            self.recent_successes,
            self.recent_failures,
        )
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in values):
            raise ValueError("backpressure counters must be non-negative integers")
        if self.latency_ms < 0 or self.observed_at < 0:
            raise ValueError("backpressure time values may not be negative")

    @property
    def attempts(self) -> int:
        return self.recent_successes + self.recent_failures

    @property
    def failure_ratio(self) -> float:
        return 0.0 if self.attempts == 0 else self.recent_failures / self.attempts


@dataclass(frozen=True)
class BackpressureDecision:
    state: BackpressureState
    concurrency_factor: float
    reason: str
    queued_ewma: float
    latency_ewma_ms: float
    failure_ratio_ewma: float
    changed: bool
    observed_at: float

    @property
    def accepts_new_work(self) -> bool:
        return self.state is not BackpressureState.PAUSED

    def bounded_parallelism(self, configured: int) -> int:
        if configured <= 0:
            raise ValueError("configured parallelism must be positive")
        if self.state is BackpressureState.PAUSED:
            return 0
        return max(1, int(configured * self.concurrency_factor))

    def to_dict(self) -> dict[str, object]:
        return {
            "state": self.state.value,
            "concurrency_factor": self.concurrency_factor,
            "reason": self.reason,
            "queued_ewma": self.queued_ewma,
            "latency_ewma_ms": self.latency_ewma_ms,
            "failure_ratio_ewma": self.failure_ratio_ewma,
            "changed": self.changed,
            "observed_at": self.observed_at,
        }


class BackpressureController:
    """Hysteretic backpressure state machine with bounded EWMAs."""

    def __init__(
        self,
        policy: BackpressurePolicy | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.policy = policy or BackpressurePolicy()
        self._clock = clock
        self._state = BackpressureState.OPEN
        self._queued_ewma = 0.0
        self._latency_ewma = 0.0
        self._failure_ewma = 0.0
        self._initialized = False
        self._recovery_streak = 0
        self._lock = threading.RLock()

    def _ewma(self, previous: float, current: float) -> float:
        alpha = self.policy.ewma_alpha
        return current if not self._initialized else alpha * current + (1 - alpha) * previous

    def _raw_state(self, sample: BackpressureSample) -> tuple[BackpressureState, str]:
        if (
            sample.queued >= self.policy.queue_critical_watermark
            or sample.claimed >= self.policy.inflight_critical_watermark
            or self._failure_ewma >= self.policy.failure_ratio_critical
            or self._latency_ewma >= self.policy.latency_critical_ms
        ):
            return BackpressureState.PAUSED, "critical pressure threshold"
        if (
            sample.queued >= self.policy.queue_high_watermark
            or sample.claimed >= self.policy.inflight_high_watermark
            or self._failure_ewma >= self.policy.failure_ratio_high
            or self._latency_ewma >= self.policy.latency_high_ms
        ):
            return BackpressureState.THROTTLED, "high pressure threshold"
        return BackpressureState.OPEN, "below pressure thresholds"

    def observe(self, sample: BackpressureSample) -> BackpressureDecision:
        with self._lock:
            self._queued_ewma = self._ewma(self._queued_ewma, float(sample.queued))
            self._latency_ewma = self._ewma(self._latency_ewma, sample.latency_ms)
            self._failure_ewma = self._ewma(self._failure_ewma, sample.failure_ratio)
            self._initialized = True
            candidate, reason = self._raw_state(sample)
            previous = self._state

            severity = {
                BackpressureState.OPEN: 0,
                BackpressureState.THROTTLED: 1,
                BackpressureState.PAUSED: 2,
            }
            if severity[candidate] > severity[self._state]:
                self._state = candidate
                self._recovery_streak = 0
            elif severity[candidate] < severity[self._state]:
                self._recovery_streak += 1
                if self._recovery_streak >= self.policy.recovery_samples:
                    if self._state is BackpressureState.PAUSED:
                        self._state = BackpressureState.THROTTLED
                    else:
                        self._state = BackpressureState.OPEN
                    self._recovery_streak = 0
                    reason = "recovery hysteresis satisfied"
                else:
                    reason = "recovery hysteresis pending"
            else:
                self._recovery_streak = 0

            factor = 1.0
            if self._state is BackpressureState.THROTTLED:
                factor = self.policy.throttle_factor
            elif self._state is BackpressureState.PAUSED:
                factor = 0.0

            return BackpressureDecision(
                state=self._state,
                concurrency_factor=factor,
                reason=reason,
                queued_ewma=self._queued_ewma,
                latency_ewma_ms=self._latency_ewma,
                failure_ratio_ewma=self._failure_ewma,
                changed=self._state is not previous,
                observed_at=sample.observed_at,
            )

    def sample_from(
        self,
        *,
        queue_counts: Mapping[str, int],
        active_workers: int,
        failed_workers: int,
        recent_successes: int,
        recent_failures: int,
        latency_ms: float,
    ) -> BackpressureDecision:
        sample = BackpressureSample(
            queued=int(queue_counts.get("queued", 0)),
            claimed=int(queue_counts.get("claimed", 0)),
            active_workers=active_workers,
            failed_workers=failed_workers,
            recent_successes=recent_successes,
            recent_failures=recent_failures,
            latency_ms=latency_ms,
            observed_at=self._clock(),
        )
        return self.observe(sample)

    @property
    def state(self) -> BackpressureState:
        with self._lock:
            return self._state

    def reset(self) -> None:
        with self._lock:
            self._state = BackpressureState.OPEN
            self._queued_ewma = 0.0
            self._latency_ewma = 0.0
            self._failure_ewma = 0.0
            self._initialized = False
            self._recovery_streak = 0

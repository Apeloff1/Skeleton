"""Bounded health and quality state for model providers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
import threading
import time
from typing import Callable


class ProviderHealth(str, Enum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    QUARANTINED = "quarantined"


@dataclass(frozen=True)
class ProviderHealthPolicy:
    failure_threshold: int = 3
    degraded_latency_ms: float = 10000.0
    unhealthy_latency_ms: float = 30000.0
    recovery_successes: int = 2

    def __post_init__(self) -> None:
        if self.failure_threshold <= 0 or self.recovery_successes <= 0:
            raise ValueError("provider health thresholds must be positive")
        if self.degraded_latency_ms <= 0:
            raise ValueError("degraded latency must be positive")
        if self.unhealthy_latency_ms < self.degraded_latency_ms:
            raise ValueError("unhealthy latency must not be below degraded latency")


@dataclass(frozen=True)
class ProviderHealthSnapshot:
    provider_id: str
    state: ProviderHealth
    attempts: int
    successes: int
    failures: int
    consecutive_failures: int
    consecutive_successes: int
    avg_latency_ms: float
    last_error_type: str
    last_observed_at: float

    @property
    def success_rate(self) -> float:
        return self.successes / self.attempts if self.attempts else 0.5

    def to_dict(self) -> dict[str, object]:
        return {
            "provider_id": self.provider_id,
            "state": self.state.value,
            "attempts": self.attempts,
            "successes": self.successes,
            "failures": self.failures,
            "consecutive_failures": self.consecutive_failures,
            "consecutive_successes": self.consecutive_successes,
            "avg_latency_ms": self.avg_latency_ms,
            "success_rate": self.success_rate,
            "last_error_type": self.last_error_type,
            "last_observed_at": self.last_observed_at,
        }


@dataclass
class _ProviderState:
    attempts: int = 0
    successes: int = 0
    failures: int = 0
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    latency_total_ms: float = 0.0
    last_error_type: str = ""
    last_observed_at: float = 0.0
    quarantined: bool = False


class ProviderHealthRegistry:
    def __init__(
        self,
        policy: ProviderHealthPolicy | None = None,
        *,
        max_providers: int = 128,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_providers <= 0:
            raise ValueError("max_providers must be positive")
        self.policy = policy or ProviderHealthPolicy()
        self.max_providers = max_providers
        self._clock = clock
        self._items: dict[str, _ProviderState] = {}
        self._lock = threading.RLock()

    def _state(self, provider_id: str) -> _ProviderState:
        if not provider_id or len(provider_id) > 256:
            raise ValueError("invalid provider_id")
        state = self._items.get(provider_id)
        if state is None:
            if len(self._items) >= self.max_providers:
                raise RuntimeError("provider health capacity exhausted")
            state = _ProviderState()
            self._items[provider_id] = state
        return state

    def record_success(self, provider_id: str, *, latency_ms: float) -> ProviderHealthSnapshot:
        if latency_ms < 0 or not math.isfinite(latency_ms):
            raise ValueError("latency must be finite and non-negative")
        with self._lock:
            state = self._state(provider_id)
            state.attempts += 1
            state.successes += 1
            state.consecutive_failures = 0
            state.consecutive_successes += 1
            state.latency_total_ms += latency_ms
            state.last_error_type = ""
            state.last_observed_at = self._clock()
            return self.snapshot(provider_id)

    def record_failure(
        self,
        provider_id: str,
        *,
        latency_ms: float = 0.0,
        error_type: str = "Error",
    ) -> ProviderHealthSnapshot:
        if latency_ms < 0 or not math.isfinite(latency_ms):
            raise ValueError("latency must be finite and non-negative")
        if len(error_type) > 256:
            raise ValueError("error_type too long")
        with self._lock:
            state = self._state(provider_id)
            state.attempts += 1
            state.failures += 1
            state.consecutive_failures += 1
            state.consecutive_successes = 0
            state.latency_total_ms += latency_ms
            state.last_error_type = error_type
            state.last_observed_at = self._clock()
            return self.snapshot(provider_id)

    def quarantine(self, provider_id: str) -> ProviderHealthSnapshot:
        with self._lock:
            state = self._state(provider_id)
            state.quarantined = True
            return self.snapshot(provider_id)

    def restore(self, provider_id: str) -> ProviderHealthSnapshot:
        with self._lock:
            state = self._state(provider_id)
            state.quarantined = False
            state.consecutive_failures = 0
            state.consecutive_successes = 0
            return self.snapshot(provider_id)

    def snapshot(self, provider_id: str) -> ProviderHealthSnapshot:
        with self._lock:
            state = self._state(provider_id)
            avg = state.latency_total_ms / state.attempts if state.attempts else 0.0
            if state.quarantined:
                health = ProviderHealth.QUARANTINED
            elif not state.attempts:
                health = ProviderHealth.UNKNOWN
            elif state.consecutive_failures >= self.policy.failure_threshold:
                health = ProviderHealth.UNHEALTHY
            elif avg >= self.policy.unhealthy_latency_ms:
                health = ProviderHealth.UNHEALTHY
            elif state.consecutive_failures or avg >= self.policy.degraded_latency_ms:
                health = ProviderHealth.DEGRADED
            else:
                health = ProviderHealth.HEALTHY
            return ProviderHealthSnapshot(
                provider_id,
                health,
                state.attempts,
                state.successes,
                state.failures,
                state.consecutive_failures,
                state.consecutive_successes,
                avg,
                state.last_error_type,
                state.last_observed_at,
            )

    def all(self) -> tuple[ProviderHealthSnapshot, ...]:
        with self._lock:
            return tuple(self.snapshot(key) for key in sorted(self._items))

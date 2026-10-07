"""Circuit breaker specifically for model planning providers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import threading
import time
from typing import Callable


class ModelCircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True)
class ModelCircuitPolicy:
    failure_threshold: int = 3
    recovery_seconds: float = 30.0
    half_open_successes: int = 1

    def __post_init__(self) -> None:
        if self.failure_threshold <= 0 or self.half_open_successes <= 0:
            raise ValueError("model circuit thresholds must be positive")
        if self.recovery_seconds < 0:
            raise ValueError("model circuit recovery must be non-negative")


@dataclass(frozen=True)
class ModelCircuitSnapshot:
    provider_id: str
    state: ModelCircuitState
    failures: int
    half_open_successes: int
    opened_at: float | None

    def to_dict(self) -> dict[str, object]:
        return {
            "provider_id": self.provider_id,
            "state": self.state.value,
            "failures": self.failures,
            "half_open_successes": self.half_open_successes,
            "opened_at": self.opened_at,
        }


@dataclass
class _State:
    state: ModelCircuitState = ModelCircuitState.CLOSED
    failures: int = 0
    half_open_successes: int = 0
    opened_at: float | None = None


class ModelCircuitOpen(RuntimeError):
    pass


class ModelCircuitRegistry:
    def __init__(
        self,
        policy: ModelCircuitPolicy | None = None,
        *,
        max_providers: int = 128,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.policy = policy or ModelCircuitPolicy()
        self.max_providers = max_providers
        self._clock = clock
        self._items: dict[str, _State] = {}
        self._lock = threading.RLock()

    def _get(self, provider_id: str) -> _State:
        if not provider_id or len(provider_id) > 256:
            raise ValueError("invalid provider_id")
        state = self._items.get(provider_id)
        if state is None:
            if len(self._items) >= self.max_providers:
                raise RuntimeError("model circuit capacity exhausted")
            state = _State()
            self._items[provider_id] = state
        return state

    def allow(self, provider_id: str) -> None:
        with self._lock:
            state = self._get(provider_id)
            if state.state is ModelCircuitState.OPEN:
                if (
                    state.opened_at is not None
                    and self._clock() - state.opened_at >= self.policy.recovery_seconds
                ):
                    state.state = ModelCircuitState.HALF_OPEN
                    state.half_open_successes = 0
                else:
                    raise ModelCircuitOpen(f"model provider circuit is open: {provider_id}")

    def success(self, provider_id: str) -> ModelCircuitSnapshot:
        with self._lock:
            state = self._get(provider_id)
            if state.state is ModelCircuitState.HALF_OPEN:
                state.half_open_successes += 1
                if state.half_open_successes >= self.policy.half_open_successes:
                    state.state = ModelCircuitState.CLOSED
                    state.failures = 0
                    state.half_open_successes = 0
                    state.opened_at = None
            else:
                state.failures = 0
            return self.snapshot(provider_id)

    def failure(self, provider_id: str) -> ModelCircuitSnapshot:
        with self._lock:
            state = self._get(provider_id)
            state.failures += 1
            state.half_open_successes = 0
            if (
                state.state is ModelCircuitState.HALF_OPEN
                or state.failures >= self.policy.failure_threshold
            ):
                state.state = ModelCircuitState.OPEN
                state.opened_at = self._clock()
            return self.snapshot(provider_id)

    def snapshot(self, provider_id: str) -> ModelCircuitSnapshot:
        with self._lock:
            state = self._get(provider_id)
            return ModelCircuitSnapshot(
                provider_id,
                state.state,
                state.failures,
                state.half_open_successes,
                state.opened_at,
            )

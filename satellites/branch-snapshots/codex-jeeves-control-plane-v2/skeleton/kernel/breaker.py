"""Circuit breakers + retry — fail-fast wrappers around flaky calls.

The kernel calls out to things that fail: model endpoints, other agents,
the vault. Two complementary patterns live here:

- :class:`RetryPolicy` — bounded retries with exponential backoff and
  decorrelated jitter, plus a predicate for which errors are retryable
  at all. Retrying a deterministic 4xx wastes everyone's time.
- :class:`CircuitBreaker` — CLOSED → OPEN on a failure threshold,
  half-open probes after a cooldown, failure-window tracking so old
  failures stop counting. While OPEN, calls fail fast with
  :class:`CircuitOpenError` instead of queueing behind a corpse.

Both are synchronous and dependency-free; async callers wrap the same
decision API.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Deque, Optional, Tuple, Type
from collections import deque

from .errors import KernelError


class RetryError(KernelError):
    code = "KRN.RETRY"


class RetriesExhausted(RetryError):
    code = "KRN.RETRY_EXHAUSTED"


class CircuitOpenError(KernelError):
    code = "KRN.CIRCUIT_OPEN"
    http_status = 503


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_s: float = 0.1
    max_delay_s: float = 5.0
    jitter: float = 0.5
    retryable: Tuple[Type[BaseException], ...] = (Exception,)

    def delay_for(self, attempt: int) -> float:
        """Exponential backoff with ±jitter decorrelation; attempt is 1-based."""
        raw = min(self.max_delay_s, self.base_delay_s * (2 ** (attempt - 1)))
        spread = raw * self.jitter
        return max(0.0, raw + random.uniform(-spread, spread))

    def is_retryable(self, exc: BaseException) -> bool:
        if isinstance(exc, KernelError) and exc.severity.value == "CRITICAL":
            return False
        return isinstance(exc, self.retryable)


class CircuitBreaker:
    """Per-dependency breaker. One breaker per downstream, not per call."""

    def __init__(
        self,
        name: str,
        *,
        failure_threshold: int = 5,
        window_s: float = 30.0,
        cooldown_s: float = 10.0,
        half_open_probes: int = 2,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        if failure_threshold < 1 or half_open_probes < 1:
            raise RetryError(
                "thresholds must be positive",
                context={"failure_threshold": failure_threshold,
                         "half_open_probes": half_open_probes},
            )
        self.name = name
        self.failure_threshold = failure_threshold
        self.window_s = window_s
        self.cooldown_s = cooldown_s
        self.half_open_probes = half_open_probes
        self._now = clock or time.monotonic
        self._state = CircuitState.CLOSED
        self._failures: Deque[float] = deque()
        self._opened_at = 0.0
        self._probe_successes = 0

    @property
    def state(self) -> CircuitState:
        if (self._state is CircuitState.OPEN
                and self._now() - self._opened_at >= self.cooldown_s):
            self._state = CircuitState.HALF_OPEN
            self._probe_successes = 0
        return self._state

    def before_call(self) -> None:
        state = self.state
        if state is CircuitState.OPEN:
            raise CircuitOpenError(
                "circuit open — failing fast",
                context={
                    "breaker": self.name,
                    "retry_after_s": round(
                        self.cooldown_s - (self._now() - self._opened_at), 3),
                },
            )

    def on_success(self) -> None:
        state = self.state
        if state is CircuitState.HALF_OPEN:
            self._probe_successes += 1
            if self._probe_successes >= self.half_open_probes:
                self._state = CircuitState.CLOSED
                self._failures.clear()
        # CLOSED: nothing to do — failures age out of the window

    def on_failure(self) -> None:
        now = self._now()
        if self.state is CircuitState.HALF_OPEN:
            self._trip(now)
            return
        cutoff = now - self.window_s
        while self._failures and self._failures[0] < cutoff:
            self._failures.popleft()
        self._failures.append(now)
        if len(self._failures) >= self.failure_threshold:
            self._trip(now)

    def _trip(self, now: float) -> None:
        self._state = CircuitState.OPEN
        self._opened_at = now
        self._failures.clear()
        self._probe_successes = 0

    def report(self) -> dict:
        return {
            "breaker": self.name,
            "state": self.state.value,
            "failures_in_window": len(self._failures),
        }


def call_with_protection(
    fn: Callable[[], object],
    *,
    policy: Optional[RetryPolicy] = None,
    breaker: Optional[CircuitBreaker] = None,
    sleep: Callable[[float], None] = time.sleep,
) -> object:
    """Retry inside the breaker: each attempt passes the gate, and the
    breaker only hears about outcomes."""
    policy = policy or RetryPolicy()
    attempt = 0
    while True:
        attempt += 1
        if breaker is not None:
            breaker.before_call()
        try:
            result = fn()
        except BaseException as exc:
            if breaker is not None:
                breaker.on_failure()
            if attempt >= policy.max_attempts or not policy.is_retryable(exc):
                if isinstance(exc, KernelError):
                    raise
                raise RetriesExhausted(
                    "attempts exhausted",
                    context={"attempts": attempt, "last_error": repr(exc)},
                    cause=exc,
                ) from exc
            sleep(policy.delay_for(attempt))
        else:
            if breaker is not None:
                breaker.on_success()
            return result

"""Resilience — circuit breakers, bulkheads, retry policies, hedged execution.

Every cross-subsystem call in Skeleton flows through a :class:`ResilienceEnvelope`
which composes, in order: bulkhead admission → circuit-breaker gate → retry with
exponential backoff + jitter → optional hedged (parallel speculative) execution.
All state transitions emit kernel events so the observability plane sees the
system's protective reflexes in real time.
"""

from __future__ import annotations

import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TypeVar

from ..kernel.errors import ResilienceError
from ..kernel.events import EventBus

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------

class BreakerState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class BreakerPolicy:
    failure_threshold: int = 5
    success_threshold: int = 2          # half-open successes needed to close
    reset_timeout: float = 30.0         # seconds before open → half-open
    window_seconds: float = 60.0        # sliding failure window


class CircuitOpenError(ResilienceError):
    def __init__(self, name: str) -> None:
        super().__init__(f"circuit '{name}' is open", code="RES.BREAKER.OPEN",
                         context={"breaker": name})


class CircuitBreaker:
    def __init__(self, name: str, policy: Optional[BreakerPolicy] = None,
                 bus: Optional[EventBus] = None) -> None:
        self.name = name
        self.policy = policy or BreakerPolicy()
        self._bus = bus
        self._state = BreakerState.CLOSED
        self._failures: List[float] = []
        self._half_open_successes = 0
        self._opened_at: Optional[float] = None
        self._lock = threading.Lock()

    @property
    def state(self) -> BreakerState:
        with self._lock:
            if (self._state == BreakerState.OPEN and self._opened_at is not None
                    and time.time() - self._opened_at >= self.policy.reset_timeout):
                self._state = BreakerState.HALF_OPEN
                self._half_open_successes = 0
                self._emit("resilience.breaker.half_open")
            return self._state

    def _emit(self, topic: str, **extra: Any) -> None:
        if self._bus:
            self._bus.publish(topic, {"breaker": self.name, **extra})

    def _prune(self) -> None:
        cutoff = time.time() - self.policy.window_seconds
        self._failures = [t for t in self._failures if t >= cutoff]

    def record_success(self) -> None:
        with self._lock:
            if self._state == BreakerState.HALF_OPEN:
                self._half_open_successes += 1
                if self._half_open_successes >= self.policy.success_threshold:
                    self._state = BreakerState.CLOSED
                    self._failures.clear()
                    self._emit("resilience.breaker.closed")
            else:
                self._prune()

    def record_failure(self) -> None:
        with self._lock:
            self._failures.append(time.time())
            self._prune()
            if self._state == BreakerState.HALF_OPEN:
                self._trip()
            elif len(self._failures) >= self.policy.failure_threshold:
                self._trip()

    def _trip(self) -> None:
        self._state = BreakerState.OPEN
        self._opened_at = time.time()
        self._emit("resilience.breaker.opened", failures=len(self._failures))

    def admit(self) -> None:
        if self.state == BreakerState.OPEN:
            raise CircuitOpenError(self.name)


# ---------------------------------------------------------------------------
# Bulkhead
# ---------------------------------------------------------------------------

class BulkheadFullError(ResilienceError):
    def __init__(self, name: str, limit: int) -> None:
        super().__init__(f"bulkhead '{name}' saturated", code="RES.BULKHEAD.FULL",
                         context={"bulkhead": name, "limit": limit})


class Bulkhead:
    """Bounded concurrency compartment — isolates one subsystem's load from another."""

    def __init__(self, name: str, limit: int, queue_limit: int = 0) -> None:
        if limit < 1:
            raise ValueError("bulkhead limit must be >= 1")
        self.name, self.limit = name, limit
        self._semaphore = threading.BoundedSemaphore(limit)
        self._in_flight = 0
        self._rejected = 0
        self._lock = threading.Lock()

    def acquire(self, timeout: Optional[float] = None) -> None:
        got = self._semaphore.acquire(timeout=timeout if timeout is not None else -1
                                      if timeout is None else timeout)
        if not got:
            with self._lock:
                self._rejected += 1
            raise BulkheadFullError(self.name, self.limit)
        with self._lock:
            self._in_flight += 1

    def release(self) -> None:
        with self._lock:
            self._in_flight -= 1
        self._semaphore.release()

    @property
    def stats(self) -> Dict[str, int]:
        with self._lock:
            return {"limit": self.limit, "in_flight": self._in_flight,
                    "rejected": self._rejected}


# ---------------------------------------------------------------------------
# Retry policy
# ---------------------------------------------------------------------------

@dataclass
class RetryPolicy:
    max_attempts: int = 3
    base_delay: float = 0.05
    max_delay: float = 2.0
    backoff_factor: float = 2.0
    jitter: float = 0.25                # fraction of delay randomised
    retryable: tuple = (Exception,)     # exception types worth retrying

    def delay_for(self, attempt: int) -> float:
        raw = min(self.max_delay, self.base_delay * (self.backoff_factor ** (attempt - 1)))
        spread = raw * self.jitter
        return max(0.0, raw + random.uniform(-spread, spread))


class RetryExhaustedError(ResilienceError):
    def __init__(self, attempts: int, last: BaseException) -> None:
        super().__init__(f"retry exhausted after {attempts} attempts: {last}",
                         code="RES.RETRY.EXHAUSTED",
                         context={"attempts": attempts, "last_error": str(last)})


# ---------------------------------------------------------------------------
# Envelope — the composition
# ---------------------------------------------------------------------------

class ResilienceEnvelope:
    """One call path: bulkhead → breaker → retry → (optional) hedging."""

    def __init__(self, name: str, bus: Optional[EventBus] = None,
                 breaker_policy: Optional[BreakerPolicy] = None,
                 bulkhead_limit: int = 64,
                 retry_policy: Optional[RetryPolicy] = None,
                 hedge_after: Optional[float] = None) -> None:
        self.name = name
        self.breaker = CircuitBreaker(name, breaker_policy, bus)
        self.bulkhead = Bulkhead(name, bulkhead_limit)
        self.retry = retry_policy or RetryPolicy()
        self.hedge_after = hedge_after
        self._bus = bus
        self._executor = ThreadPoolExecutor(max_workers=bulkhead_limit + 4)

    def call(self, fn: Callable[[], T]) -> T:
        self.breaker.admit()
        self.bulkhead.acquire(timeout=self.retry.max_delay)
        try:
            result = self._run_with_retry(fn)
            self.breaker.record_success()
            return result
        except Exception:
            self.breaker.record_failure()
            raise
        finally:
            self.bulkhead.release()

    def _run_with_retry(self, fn: Callable[[], T]) -> T:
        last: Optional[BaseException] = None
        for attempt in range(1, self.retry.max_attempts + 1):
            try:
                if self.hedge_after is not None:
                    return self._hedged(fn)
                return fn()
            except self.retry.retryable as exc:
                last = exc
                if attempt < self.retry.max_attempts:
                    time.sleep(self.retry.delay_for(attempt))
            except BaseException:
                raise
        raise RetryExhaustedError(self.retry.max_attempts, last or RuntimeError("unknown"))

    def _hedged(self, fn: Callable[[], T]) -> T:
        """Fire the primary, then a speculative duplicate after `hedge_after` seconds;
        first success wins, the loser is abandoned."""
        futures = [self._executor.submit(fn)]
        try:
            deadline = time.time() + (self.hedge_after or 0)
            while True:
                done = [f for f in futures if f.done()]
                for f in done:
                    exc = f.exception()
                    if exc is None:
                        return f.result()
                if time.time() >= deadline and len(futures) == 1:
                    futures.append(self._executor.submit(fn))
                if all(f.done() for f in futures):
                    raise futures[0].exception() or ResilienceError(
                        "all hedged attempts failed", code="RES.HEDGE.FAILED")
                time.sleep(0.001)
        finally:
            for f in futures:
                f.cancel()

    def stats(self) -> Dict[str, Any]:
        return {"name": self.name, "breaker": self.breaker.state.value,
                "bulkhead": self.bulkhead.stats,
                "hedge_after": self.hedge_after,
                "retry_attempts": self.retry.max_attempts}

"""coalesce_depth — waiter limits, TTL flights, metrics over Coalescer.

Extends ``skeleton.kernel.coalesce.Coalescer`` with a keyed flight board
used by Pack A admit decision caching and stampede-safe get_or_compute.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, TypeVar

from skeleton.kernel.coalesce import Coalescer

T = TypeVar("T")


class WaiterLimitExceeded(RuntimeError):
    """Too many waiters on a single in-flight key."""


class CoalesceTimeout(TimeoutError):
    """Waiter exceeded flight wait budget."""


@dataclass
class CoalesceMetrics:
    leaders: int = 0
    joiners: int = 0
    successes: int = 0
    failures: int = 0
    timeouts: int = 0
    waiter_limit_hits: int = 0
    expired_flights: int = 0

    def as_dict(self) -> Dict[str, int]:
        return {
            "leaders": self.leaders,
            "joiners": self.joiners,
            "successes": self.successes,
            "failures": self.failures,
            "timeouts": self.timeouts,
            "waiter_limit_hits": self.waiter_limit_hits,
            "expired_flights": self.expired_flights,
        }


@dataclass
class FlightRecord:
    key: str
    started: float
    waiter_count: int
    done: bool
    error: Optional[str] = None


class WaiterQueue:
    """Bounded waiter set for one flight."""

    def __init__(self, max_waiters: int) -> None:
        if max_waiters < 1:
            raise ValueError("max_waiters must be >= 1")
        self.max_waiters = int(max_waiters)
        self._count = 0
        self._lock = threading.Lock()

    def try_join(self) -> bool:
        with self._lock:
            if self._count >= self.max_waiters:
                return False
            self._count += 1
            return True

    def leave(self) -> None:
        with self._lock:
            self._count = max(0, self._count - 1)

    @property
    def count(self) -> int:
        with self._lock:
            return self._count


class _Flight:
    def __init__(self, key: str, max_waiters: int) -> None:
        self.key = key
        self._done = threading.Event()
        self._result: Any = None
        self._error: Optional[BaseException] = None
        self.started = time.monotonic()
        self.waiters = WaiterQueue(max_waiters)
        self.leader_registered = False

    def succeed(self, value: Any) -> None:
        self._result = value
        self._done.set()

    def fail(self, exc: BaseException) -> None:
        self._error = exc
        self._done.set()

    def wait(self, timeout: Optional[float]) -> Any:
        ok = self._done.wait(timeout=timeout)
        if not ok:
            raise CoalesceTimeout(f"timeout waiting for flight {self.key!r}")
        if self._error is not None:
            raise self._error
        return self._result

    def record(self) -> FlightRecord:
        return FlightRecord(
            key=self.key,
            started=self.started,
            waiter_count=self.waiters.count,
            done=self._done.is_set(),
            error=None if self._error is None else type(self._error).__name__,
        )


class KeyedFlightBoard:
    """Single-flight board with per-key waiter caps and optional wait TTL."""

    def __init__(
        self,
        *,
        max_waiters_per_key: int = 64,
        default_wait_timeout: Optional[float] = 5.0,
        max_inflight_keys: int = 4096,
    ) -> None:
        self.max_waiters_per_key = int(max_waiters_per_key)
        self.default_wait_timeout = default_wait_timeout
        self.max_inflight_keys = int(max_inflight_keys)
        self._lock = threading.Lock()
        self._flights: Dict[str, _Flight] = {}
        self.metrics = CoalesceMetrics()
        self._inner = Coalescer()

    def get(
        self,
        key: str,
        fetch_fn: Callable[[], T],
        *,
        timeout: Optional[float] = None,
    ) -> T:
        wait_timeout = self.default_wait_timeout if timeout is None else timeout
        leader = False
        with self._lock:
            flight = self._flights.get(key)
            if flight is None:
                if len(self._flights) >= self.max_inflight_keys:
                    # Fail closed under key explosion — run uncoalesced once.
                    self.metrics.expired_flights += 1
                else:
                    flight = _Flight(key, self.max_waiters_per_key)
                    self._flights[key] = flight
                    leader = True
                    self.metrics.leaders += 1
            else:
                if not flight.waiters.try_join():
                    self.metrics.waiter_limit_hits += 1
                    raise WaiterLimitExceeded(f"waiter limit for {key!r}")
                self.metrics.joiners += 1

        if not leader:
            try:
                return flight.wait(wait_timeout)
            except CoalesceTimeout:
                self.metrics.timeouts += 1
                raise
            finally:
                flight.waiters.leave()

        try:
            result = fetch_fn()
            flight.succeed(result)
            self.metrics.successes += 1
            return result
        except Exception as exc:
            flight.fail(exc)
            self.metrics.failures += 1
            raise
        finally:
            with self._lock:
                if self._flights.get(key) is flight:
                    del self._flights[key]

    def inflight_records(self) -> List[FlightRecord]:
        with self._lock:
            return [f.record() for f in self._flights.values()]

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            inflight = len(self._flights)
        return {
            "inflight_keys": inflight,
            "max_inflight_keys": self.max_inflight_keys,
            "max_waiters_per_key": self.max_waiters_per_key,
            "metrics": self.metrics.as_dict(),
        }

    def simple_coalesce(self, key: str, fetch_fn: Callable[[], T]) -> T:
        """Thin passthrough to root Coalescer for callers that need bare semantics."""
        return self._inner.get(key, fetch_fn)


def coalesce_get_or_compute(
    board: KeyedFlightBoard,
    key: str,
    compute: Callable[[], T],
    *,
    timeout: Optional[float] = None,
) -> T:
    return board.get(key, compute, timeout=timeout)


_BOARD = KeyedFlightBoard()


def default_board() -> KeyedFlightBoard:
    return _BOARD


def reset_default_board_for_tests() -> None:
    global _BOARD
    _BOARD = KeyedFlightBoard()


# Route-priority coalesce keys for admit depth
def admit_coalesce_key(method: str, path: str, idempotency_key: Optional[str] = None) -> str:
    if idempotency_key:
        return f"idem:{idempotency_key}"
    return f"{method.upper()}:{path}"


# Explicit key namespaces used by Pack A (stable contract surface)
COALESCE_NAMESPACES = (
    "admit.decision",
    "admit.staging",
    "cache.fill",
    "forge.materialise",
    "gameforge.run",
    "swarm.fence",
    "telemetry.batch",
)


def namespaced_key(namespace: str, key: str) -> str:
    if namespace not in COALESCE_NAMESPACES:
        # allow extension prefixes under pack_a.*
        if not namespace.startswith("pack_a."):
            raise ValueError(f"unknown coalesce namespace: {namespace}")
    return f"{namespace}:{key}"


__all__ = [
    "COALESCE_NAMESPACES",
    "CoalesceMetrics",
    "CoalesceTimeout",
    "FlightRecord",
    "KeyedFlightBoard",
    "WaiterLimitExceeded",
    "WaiterQueue",
    "admit_coalesce_key",
    "coalesce_get_or_compute",
    "default_board",
    "namespaced_key",
    "reset_default_board_for_tests",
]

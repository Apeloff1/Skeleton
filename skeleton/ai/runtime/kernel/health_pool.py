"""health_pool — generic health-checked connection pool (gameforge-rs pool::HealthPool).

Connections are probed on checkout and proactively replaced after ``max_age_sec``.
Idle pool is hard-capped at ``cap``; overflow on checkin is dropped.

Sibling source: ``/workspace/chaos-scout/gf-pool.rs`` (also gf-services-lib.rs pool).

Threading-based sync port — no asyncio. Does not touch coalesce / buffer_pool /
chaos / adaptive_gate / cortex / jeeves.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, Generic, List, Tuple, TypeVar

T = TypeVar("T")


class HealthPool(Generic[T]):
    """Sync port of gf ``pool::HealthPool<T>``.

    Parameters
    ----------
    make_fn:
        Factory invoked when the idle pool has no healthy connection.
    check_fn:
        Health probe; return False to discard the connection on checkout.
    cap:
        Max idle connections retained after checkin.
    max_age_sec:
        Connections older than this are replaced on checkout.
    """

    def __init__(
        self,
        make_fn: Callable[[], T],
        check_fn: Callable[[T], bool],
        cap: int,
        max_age_sec: float,
    ) -> None:
        if cap < 0:
            raise ValueError("cap must be non-negative")
        if max_age_sec < 0:
            raise ValueError("max_age_sec must be non-negative")
        self._make = make_fn
        self._check = check_fn
        self._cap = int(cap)
        self._max_age_sec = float(max_age_sec)
        self._idle: List[Tuple[T, float]] = []
        self._checkouts = 0
        self._replaced = 0
        self._lock = threading.Lock()

    def checkout(self) -> T:
        """Pop a healthy, non-aged idle connection, or create a fresh one."""
        with self._lock:
            self._checkouts += 1
            while self._idle:
                conn, born = self._idle.pop()
                age = time.monotonic() - born
                if age < self._max_age_sec and self._check(conn):
                    return conn
                self._replaced += 1
        return self._make()

    def checkin(self, conn: T) -> None:
        """Return a connection to the idle pool if under cap; else drop it."""
        with self._lock:
            if len(self._idle) < self._cap:
                self._idle.append((conn, time.monotonic()))

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "checkouts": self._checkouts,
                "replaced": self._replaced,
            }

    @property
    def checkouts(self) -> int:
        with self._lock:
            return self._checkouts

    @property
    def replaced(self) -> int:
        with self._lock:
            return self._replaced

    @property
    def idle_count(self) -> int:
        with self._lock:
            return len(self._idle)

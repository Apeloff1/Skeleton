"""coalesce — single-flight request merge (gameforge-rs coalesce::Coalescer port).

Concurrent callers for the same key share one in-flight ``fetch_fn``.
The first thread to claim a key is the leader; later waiters block on
the same flight. Success and errors are delivered to every waiter.

Sibling source: ``/workspace/chaos-scout/gf-coalesce.rs``.

Threading-based sync port — no asyncio, no chaos/gate edits.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Dict, Optional, TypeVar


T = TypeVar("T")


class _Flight:
    def __init__(self) -> None:
        self._done = threading.Event()
        self._result: Any = None
        self._error: Optional[BaseException] = None

    def succeed(self, value: Any) -> None:
        self._result = value
        self._done.set()

    def fail(self, exc: BaseException) -> None:
        self._error = exc
        self._done.set()

    def wait(self) -> Any:
        self._done.wait()
        if self._error is not None:
            raise self._error
        return self._result


class Coalescer:
    """Same-key concurrent ``get`` shares one in-flight fetch."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._in_flight: Dict[str, _Flight] = {}

    def get(self, key: str, fetch_fn: Callable[[], T]) -> T:
        leader = False
        with self._lock:
            flight = self._in_flight.get(key)
            if flight is None:
                flight = _Flight()
                self._in_flight[key] = flight
                leader = True

        if not leader:
            return flight.wait()

        try:
            result = fetch_fn()
            flight.succeed(result)
            return result
        except Exception as exc:
            flight.fail(exc)
            raise
        finally:
            with self._lock:
                if self._in_flight.get(key) is flight:
                    del self._in_flight[key]

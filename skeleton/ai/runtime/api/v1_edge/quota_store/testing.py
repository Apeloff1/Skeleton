"""Test double for an outside (Redis-style) counter backend.

:class:`FakeRemoteClient` implements the client surface that
:class:`~.remote.RemoteCounterStore` expects, with the same server-side
semantics as :data:`~.remote.TAKE_SCRIPT` (hash per key, PEXPIRE TTL) and
knobs to inject outages, latency budgets and corrupt replies. Two edge
"replicas" sharing one ``FakeRemoteClient`` behave like two processes
sharing one Redis.
"""
from __future__ import annotations

import threading
from typing import Callable, Dict, List, Optional, Tuple

from .store import BucketSpec, compute_take


class FakeConnectionError(ConnectionError):
    pass


class FakeTimeout(TimeoutError):
    pass


class FakeRemoteClient:
    def __init__(self, *, clock: Optional[Callable[[], float]] = None):
        self._lock = threading.Lock()
        self._hash: Dict[str, Tuple[float, float]] = {}
        self._expires_ms: Dict[str, float] = {}
        self._clock = clock
        self._server_now_ms = float("-inf")
        self.down = False
        self.timeout = False
        self.corrupt = False
        self.calls: List[str] = []

    def _now_ms(self, fallback_s: float) -> float:
        # Redis PEXPIRE uses the server clock, not the caller's potentially
        # regressed refill timestamp. Test clocks must preserve monotone TTL
        # progression or a rollback could erase quota custody in the fixture.
        observed = (self._clock() if self._clock else fallback_s) * 1000.0
        self._server_now_ms = max(self._server_now_ms, observed)
        return self._server_now_ms

    def _check(self, op: str) -> None:
        self.calls.append(op)
        if self.down:
            raise FakeConnectionError("connection refused")
        if self.timeout:
            raise FakeTimeout("deadline exceeded")

    def _expire(self, key: str, now_ms: float) -> None:
        exp = self._expires_ms.get(key)
        if exp is not None and now_ms >= exp:
            self._hash.pop(key, None)
            self._expires_ms.pop(key, None)

    def eval_take(self, key: str, capacity: float, rate: float, cost: float,
                  now: float, ttl_ms: int):
        self._check("eval_take")
        with self._lock:
            now_ms = self._now_ms(now)
            self._expire(key, now_ms)
            row = self._hash.get(key)
            tokens, updated = row if row else (None, None)
            # Match Redis Lua high-water timestamp behavior under skew.
            effective_now = max(now, updated) if updated is not None else now
            res, level = compute_take(tokens, updated, BucketSpec(capacity, rate), cost, effective_now)
            self._hash[key] = (level, effective_now)
            self._expires_ms[key] = now_ms + ttl_ms
        if self.corrupt:
            return (7, "nan")
        return (1 if res.allowed else 0, repr(level))

    def get_bucket(self, key: str):
        self._check("get_bucket")
        with self._lock:
            row = self._hash.get(key)
            return None if row is None else (repr(row[0]), repr(row[1]))

    def delete(self, key: str) -> int:
        self._check("delete")
        with self._lock:
            self._expires_ms.pop(key, None)
            return 1 if self._hash.pop(key, None) is not None else 0

    def ping(self) -> bool:
        self._check("ping")
        return True

    def keys(self) -> List[str]:
        with self._lock:
            return sorted(self._hash)


class FlakyCounterStore:
    """Wraps any CounterStore and raises StoreUnavailable when ``down`` is set."""

    def __init__(self, inner, *, name: str = "flaky"):
        self.inner = inner
        self.name = name
        self.down = False

    def _gate(self):
        from .store import StoreUnavailable
        if self.down:
            raise StoreUnavailable("injected outage", backend=self.name)

    def take(self, key, spec, cost=1.0, now=None):
        self._gate()
        return self.inner.take(key, spec, cost, now)

    def peek(self, key, spec, now=None):
        self._gate()
        return self.inner.peek(key, spec, now)

    def reset(self, key):
        self._gate()
        self.inner.reset(key)

    def healthy(self):
        return not self.down and self.inner.healthy()

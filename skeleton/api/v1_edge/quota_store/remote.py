"""Remote (Redis-style) :class:`CounterStore` adapter.

The adapter talks to any client exposing the small surface below, which a
thin wrapper over redis-py provides in production (``EVALSHA`` of
:data:`TAKE_SCRIPT` plus ``DEL``/``PING``). No redis dependency is imported
here; tests use :class:`skeleton.api.v1_edge.quota_store.testing.FakeRemoteClient`.

Client surface (duck-typed)::

    eval_take(key, capacity, rate_per_s, cost, now, ttl_ms) -> (allowed:int, tokens:str)
    get_bucket(key) -> Optional[(tokens:str, updated:str)]
    delete(key) -> int
    ping() -> bool

Every client exception — and any malformed reply — becomes
:class:`StoreUnavailable`. A per-call deadline is enforced by the client; the
adapter adds a circuit: after ``trip_after`` consecutive failures it stops
calling the backend for ``cooldown_s`` and fails closed immediately, so a dead
store costs the edge microseconds instead of a timeout per request.
"""
from __future__ import annotations

import math
import threading
import time
from typing import Any, Callable, Optional

from .store import BucketSpec, StoreUnavailable, TakeResult, compute_take

# Atomic refill+spend, executed server-side. Mirrors store.compute_take exactly.
TAKE_SCRIPT = """
local key      = KEYS[1]
local capacity = tonumber(ARGV[1])
local rate     = tonumber(ARGV[2])
local cost     = tonumber(ARGV[3])
local now      = tonumber(ARGV[4])
local ttl_ms   = tonumber(ARGV[5])
local row      = redis.call('HMGET', key, 'tokens', 'updated')
local tokens   = tonumber(row[1])
local updated  = tonumber(row[2])
if tokens == nil or updated == nil then
  tokens = capacity
  updated = now
end
local elapsed = math.max(0, now - updated)
local level = math.min(capacity, tokens + elapsed * rate)
local allowed = 0
if cost <= capacity and level + 1e-9 >= cost then
  level = level - cost
  allowed = 1
end
redis.call('HSET', key, 'tokens', tostring(level), 'updated', tostring(now))
redis.call('PEXPIRE', key, ttl_ms)
return {allowed, tostring(level)}
"""


class RemoteCounterStore:
    name = "remote"

    def __init__(self, client: Any, *, prefix: str = "skq:", trip_after: int = 3,
                 cooldown_s: float = 2.0, clock: Callable[[], float] = time.time):
        if trip_after < 1:
            raise ValueError("trip_after must be >= 1")
        self._client = client
        self._prefix = prefix
        self._trip_after = trip_after
        self._cooldown = cooldown_s
        self._clock = clock
        self._lock = threading.Lock()
        self._failures = 0
        self._open_until = 0.0

    # -- circuit --------------------------------------------------------------------
    def _guard(self) -> None:
        with self._lock:
            if self._open_until and self._clock() < self._open_until:
                raise StoreUnavailable("counter store circuit open", backend=self.name)

    def _ok(self) -> None:
        with self._lock:
            self._failures, self._open_until = 0, 0.0

    def _fail(self, exc: BaseException) -> StoreUnavailable:
        with self._lock:
            self._failures += 1
            if self._failures >= self._trip_after:
                self._open_until = self._clock() + self._cooldown
        return StoreUnavailable(f"counter store error: {type(exc).__name__}", backend=self.name)

    @property
    def circuit_open(self) -> bool:
        with self._lock:
            return bool(self._open_until) and self._clock() < self._open_until

    def _k(self, key: str) -> str:
        return self._prefix + key

    # -- CounterStore -------------------------------------------------------------
    def take(self, key: str, spec: BucketSpec, cost: float = 1.0,
             now: Optional[float] = None) -> TakeResult:
        if cost <= 0 or not math.isfinite(cost):
            raise ValueError("cost must be positive and finite")
        self._guard()
        t = self._clock() if now is None else now
        ttl_ms = max(1, int(math.ceil(spec.full_after_s * 1000)))
        try:
            reply = self._client.eval_take(self._k(key), spec.capacity, spec.rate_per_s, cost, t, ttl_ms)
            allowed, level = int(reply[0]), float(reply[1])
            if (not math.isfinite(level) or not -1e-9 <= level <= spec.capacity + 1e-9
                    or allowed not in (0, 1) or type(reply) not in (list, tuple)
                    or len(reply) != 2):
                raise ValueError("malformed reply")
        except StoreUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001 - any backend fault fails closed
            raise self._fail(exc) from exc
        self._ok()
        level = max(0.0, min(spec.capacity, level))
        reset = (spec.capacity - level) / spec.rate_per_s
        if allowed:
            return TakeResult(True, level, spec.capacity, 0.0, reset)
        wait = math.inf if cost > spec.capacity else (cost - level) / spec.rate_per_s
        return TakeResult(False, level, spec.capacity, wait, reset)

    def peek(self, key: str, spec: BucketSpec, now: Optional[float] = None) -> TakeResult:
        self._guard()
        t = self._clock() if now is None else now
        try:
            row = self._client.get_bucket(self._k(key))
            tokens = updated = None
            if row is not None:
                tokens, updated = float(row[0]), float(row[1])
                if (not math.isfinite(tokens) or not math.isfinite(updated)
                        or tokens < 0 or tokens > spec.capacity + 1e-9):
                    raise ValueError("corrupt remote token bucket")
        except Exception as exc:  # noqa: BLE001
            raise self._fail(exc) from exc
        self._ok()
        if tokens is None:
            tokens, updated = spec.capacity, t
        level = min(spec.capacity, tokens + max(0.0, t - updated) * spec.rate_per_s)
        ok = level + 1e-9 >= 1
        return TakeResult(ok, level, spec.capacity, 0.0 if ok else (1 - level) / spec.rate_per_s,
                          (spec.capacity - level) / spec.rate_per_s)

    def reset(self, key: str) -> None:
        self._guard()
        try:
            self._client.delete(self._k(key))
        except Exception as exc:  # noqa: BLE001
            raise self._fail(exc) from exc
        self._ok()

    def healthy(self) -> bool:
        if self.circuit_open:
            return False
        try:
            return bool(self._client.ping())
        except Exception:  # noqa: BLE001 - health probes never raise
            return False


__all__ = ["RemoteCounterStore", "TAKE_SCRIPT", "compute_take"]

"""Thread-safe bounded serving capacity and idempotent reservation ledger.

Reservations are capacity claims, not authorization. Call admission first.
The ledger never executes model code, and a failed acquisition never consumes
capacity. It is process-local; production multi-process serving requires a
transactional shared store before enabling multiple workers.
"""
from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Callable
import time


class CapacityDenied(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CapacityLimits:
    max_active: int
    max_reserved_tokens: int
    lease_ns: int

    def __post_init__(self):
        for value in (self.max_active, self.max_reserved_tokens, self.lease_ns):
            if type(value) is not int or value <= 0:
                raise ValueError("positive integer limits required")


@dataclass(frozen=True, slots=True)
class Reservation:
    request_id: str
    fingerprint: str
    tokens: int
    expires_ns: int
    sequence: int


class CapacityLedger:
    def __init__(self, limits: CapacityLimits, *, clock_ns: Callable[[], int] = time.monotonic_ns):
        if not isinstance(limits, CapacityLimits) or not callable(clock_ns):
            raise TypeError("limits and clock required")
        self.limits = limits
        self._clock = clock_ns
        self._lock = RLock()
        self._active: dict[str, Reservation] = {}
        self._sequence = 0

    def _now(self) -> int:
        value = self._clock()
        if type(value) is not int or value < 0:
            raise CapacityDenied("invalid monotonic clock")
        return value

    def _reap(self, now: int) -> None:
        for key, lease in tuple(self._active.items()):
            if lease.expires_ns <= now:
                del self._active[key]

    def acquire(self, request_id: str, fingerprint: str, tokens: int, *, exclusive: bool = False) -> Reservation:
        if type(exclusive) is not bool:
            raise CapacityDenied("exclusive must be a boolean")
        if (not isinstance(request_id, str) or not request_id or len(request_id) > 256
                or not isinstance(fingerprint, str) or not fingerprint or len(fingerprint) > 256
                or type(tokens) is not int or tokens <= 0):
            raise CapacityDenied("invalid reservation identity or tokens")
        with self._lock:
            now = self._now()
            self._reap(now)
            previous = self._active.get(request_id)
            if previous is not None:
                if previous.fingerprint != fingerprint or previous.tokens != tokens:
                    raise CapacityDenied("idempotency key conflict")
                if exclusive:
                    raise CapacityDenied("request already has an active reservation")
                return previous
            if len(self._active) >= self.limits.max_active:
                raise CapacityDenied("active request capacity exhausted")
            if tokens > self.limits.max_reserved_tokens - sum(r.tokens for r in self._active.values()):
                raise CapacityDenied("token capacity exhausted")
            self._sequence += 1
            lease = Reservation(request_id, fingerprint, tokens,
                                now + self.limits.lease_ns, self._sequence)
            self._active[request_id] = lease
            return lease

    def release(self, lease: Reservation) -> bool:
        if not isinstance(lease, Reservation):
            raise TypeError("Reservation required")
        with self._lock:
            current = self._active.get(lease.request_id)
            if current != lease:
                return False
            del self._active[lease.request_id]
            return True

    def is_active(self, lease: Reservation) -> bool:
        if not isinstance(lease, Reservation):
            return False
        with self._lock:
            self._reap(self._now())
            return self._active.get(lease.request_id) == lease

    def snapshot(self) -> tuple[int, int]:
        with self._lock:
            self._reap(self._now())
            return len(self._active), sum(r.tokens for r in self._active.values())

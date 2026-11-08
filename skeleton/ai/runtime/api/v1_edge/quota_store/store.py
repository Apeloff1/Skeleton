"""Shared counter-store contract for distributed /api/v1 quotas.

A :class:`CounterStore` holds token buckets that several edge replicas share.
The one operation that matters is :meth:`CounterStore.take`: refill a bucket
from elapsed time, then try to remove ``cost`` tokens, *atomically*. Doing the
refill and the spend in one step is what keeps two replicas from both
spending the last token.

Stores raise :class:`StoreUnavailable` for any backend failure (connection,
timeout, corrupt state). The limiter turns that into a fail-closed 503; a
store must never "guess" an allow.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable


class StoreUnavailable(Exception):
    """The shared counter store could not answer; callers must fail closed."""

    def __init__(self, message: str = "counter store unavailable", *, backend: str = "unknown"):
        super().__init__(message)
        self.backend = backend


@dataclass(frozen=True)
class BucketSpec:
    """Shape of one token bucket: ``capacity`` tokens, refilled at ``rate_per_s``."""

    capacity: float
    rate_per_s: float

    def __post_init__(self) -> None:
        if not (self.capacity >= 1 and math.isfinite(self.capacity)):
            raise ValueError("capacity must be >= 1 and finite")
        if not (self.rate_per_s > 0 and math.isfinite(self.rate_per_s)):
            raise ValueError("rate_per_s must be positive and finite")

    @property
    def full_after_s(self) -> float:
        """Seconds for an empty bucket to refill completely (used as the key TTL)."""
        return self.capacity / self.rate_per_s


@dataclass(frozen=True)
class TakeResult:
    """Outcome of one atomic take."""

    allowed: bool
    remaining: float
    capacity: float
    retry_after_s: float  # 0 when allowed
    reset_after_s: float  # seconds until the bucket is full again

    @property
    def remaining_int(self) -> int:
        return max(0, int(math.floor(self.remaining + 1e-9)))


def compute_take(tokens: Optional[float], updated: Optional[float], spec: BucketSpec,
                 cost: float, now: float) -> "tuple[TakeResult, float]":
    """Pure token-bucket step shared by every store implementation.

    Returns the result and the new token count to persist (with ``now`` as the
    new update time). A missing bucket starts full. Clock skew backwards is
    treated as zero elapsed time, never as negative refill.
    """
    if cost <= 0 or not math.isfinite(cost):
        raise ValueError("cost must be positive and finite")
    if tokens is None or updated is None:
        tokens, updated = spec.capacity, now
    elapsed = max(0.0, now - updated)
    level = min(spec.capacity, tokens + elapsed * spec.rate_per_s)
    if cost > spec.capacity:
        # Can never succeed; report the wait for a full bucket, do not spend.
        return (TakeResult(False, level, spec.capacity, math.inf,
                           (spec.capacity - level) / spec.rate_per_s), level)
    if level + 1e-9 >= cost:
        level -= cost
        return (TakeResult(True, level, spec.capacity, 0.0,
                           (spec.capacity - level) / spec.rate_per_s), level)
    wait = (cost - level) / spec.rate_per_s
    return (TakeResult(False, level, spec.capacity, wait,
                       (spec.capacity - level) / spec.rate_per_s), level)


@runtime_checkable
class CounterStore(Protocol):
    """Interface every shared counter backend implements."""

    name: str

    def take(self, key: str, spec: BucketSpec, cost: float = 1.0,
             now: Optional[float] = None) -> TakeResult:
        """Atomically refill and spend. Raises :class:`StoreUnavailable`."""
        ...

    def peek(self, key: str, spec: BucketSpec, now: Optional[float] = None) -> TakeResult:
        """Read the bucket level without spending. Raises :class:`StoreUnavailable`."""
        ...

    def reset(self, key: str) -> None:
        """Forget one bucket (operator action, e.g. after raising a tenant's plan)."""
        ...

    def healthy(self) -> bool:
        """Cheap liveness probe for /health/ready; must not raise."""
        ...

"""Deterministic token-bucket rate limiting for swarm ingress."""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Callable


@dataclass(slots=True)
class Bucket:
    capacity: float
    refill_per_second: float
    tokens: float
    updated_at: float


class TokenBucketLimiter:
    def __init__(self, *, capacity: float, refill_per_second: float, clock: Callable[[], float] = monotonic) -> None:
        if capacity <= 0 or refill_per_second <= 0:
            raise ValueError("capacity and refill_per_second must be positive")
        self.capacity = float(capacity)
        self.refill_per_second = float(refill_per_second)
        self._clock = clock
        self._buckets: dict[str, Bucket] = {}

    def allow(self, key: str, *, cost: float = 1.0) -> bool:
        if cost <= 0:
            raise ValueError("cost must be positive")
        now = self._clock()
        bucket = self._buckets.setdefault(key, Bucket(self.capacity, self.refill_per_second, self.capacity, now))
        elapsed = max(0.0, now - bucket.updated_at)
        bucket.tokens = min(bucket.capacity, bucket.tokens + elapsed * bucket.refill_per_second)
        bucket.updated_at = now
        if bucket.tokens < cost:
            return False
        bucket.tokens -= cost
        return True

    def remaining(self, key: str) -> float:
        bucket = self._buckets.get(key)
        return self.capacity if bucket is None else bucket.tokens

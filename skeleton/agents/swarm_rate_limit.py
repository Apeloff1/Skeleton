"""Deterministic, thread-safe token-bucket rate limiting for swarm ingress."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
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
        self._lock = RLock()

    @staticmethod
    def _key(key: str) -> str:
        normalized = key.strip()
        if not normalized:
            raise ValueError("rate-limit key must not be empty")
        return normalized

    def _refill(self, bucket: Bucket, now: float) -> None:
        elapsed = max(0.0, now - bucket.updated_at)
        bucket.tokens = min(bucket.capacity, bucket.tokens + elapsed * bucket.refill_per_second)
        bucket.updated_at = now

    def allow(self, key: str, *, cost: float = 1.0) -> bool:
        if cost <= 0:
            raise ValueError("cost must be positive")
        key = self._key(key)
        with self._lock:
            now = self._clock()
            bucket = self._buckets.setdefault(
                key,
                Bucket(self.capacity, self.refill_per_second, self.capacity, now),
            )
            self._refill(bucket, now)
            if bucket.tokens < cost:
                return False
            bucket.tokens -= cost
            return True

    def remaining(self, key: str) -> float:
        key = self._key(key)
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                return self.capacity
            self._refill(bucket, self._clock())
            return bucket.tokens

    def reset(self, key: str) -> bool:
        key = self._key(key)
        with self._lock:
            return self._buckets.pop(key, None) is not None

    def snapshot(self) -> dict[str, dict[str, float]]:
        with self._lock:
            now = self._clock()
            result: dict[str, dict[str, float]] = {}
            for key, bucket in sorted(self._buckets.items()):
                self._refill(bucket, now)
                result[key] = {
                    "capacity": bucket.capacity,
                    "refill_per_second": bucket.refill_per_second,
                    "tokens": bucket.tokens,
                    "updated_at": bucket.updated_at,
                }
            return result

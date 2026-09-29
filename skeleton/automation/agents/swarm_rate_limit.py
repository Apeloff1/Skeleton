"""Deterministic, thread-safe token-bucket rate limiting for swarm ingress."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
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
        capacity = self._positive_finite(capacity, "capacity")
        refill_per_second = self._positive_finite(refill_per_second, "refill_per_second")
        self.capacity = capacity
        self.refill_per_second = refill_per_second
        self._clock = clock
        self._buckets: dict[str, Bucket] = {}
        self._lock = RLock()

    @staticmethod
    def _positive_finite(value: float, name: str) -> float:
        value = float(value)
        if not isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be a positive finite number")
        return value

    @staticmethod
    def _key(key: str) -> str:
        normalized = key.strip()
        if not normalized:
            raise ValueError("rate-limit key must not be empty")
        return normalized

    @classmethod
    def _cost(cls, cost: float) -> float:
        return cls._positive_finite(cost, "cost")

    def _now(self) -> float:
        now = float(self._clock())
        if not isfinite(now):
            raise ValueError("clock must return a finite number")
        return now

    def _refill(self, bucket: Bucket, now: float) -> None:
        elapsed = max(0.0, now - bucket.updated_at)
        bucket.tokens = min(bucket.capacity, bucket.tokens + elapsed * bucket.refill_per_second)
        bucket.updated_at = now

    def allow(self, key: str, *, cost: float = 1.0) -> bool:
        cost = self._cost(cost)
        key = self._key(key)
        with self._lock:
            now = self._now()
            bucket = self._buckets.setdefault(
                key,
                Bucket(self.capacity, self.refill_per_second, self.capacity, now),
            )
            self._refill(bucket, now)
            if bucket.tokens < cost:
                return False
            bucket.tokens -= cost
            return True

    def refund(self, key: str, *, cost: float = 1.0) -> float:
        """Return previously consumed capacity without exceeding bucket capacity."""
        cost = self._cost(cost)
        key = self._key(key)
        with self._lock:
            now = self._now()
            bucket = self._buckets.setdefault(
                key,
                Bucket(self.capacity, self.refill_per_second, self.capacity, now),
            )
            self._refill(bucket, now)
            bucket.tokens = min(bucket.capacity, bucket.tokens + cost)
            return bucket.tokens

    def remaining(self, key: str) -> float:
        key = self._key(key)
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                return self.capacity
            self._refill(bucket, self._now())
            return bucket.tokens

    def reset(self, key: str) -> bool:
        key = self._key(key)
        with self._lock:
            return self._buckets.pop(key, None) is not None

    def snapshot(self) -> dict[str, dict[str, float]]:
        with self._lock:
            now = self._now()
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

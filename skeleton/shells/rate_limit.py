"""Deterministic token-bucket rate limiting for shell admissions."""

from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Callable


@dataclass(frozen=True)
class RateLimitPolicy:
    capacity: float = 10.0
    refill_per_second: float = 1.0
    cost_per_execution: float = 1.0

    def __post_init__(self) -> None:
        if self.capacity <= 0 or self.refill_per_second < 0 or self.cost_per_execution <= 0:
            raise ValueError("invalid rate-limit policy")
        if self.cost_per_execution > self.capacity:
            raise ValueError("execution cost cannot exceed bucket capacity")


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    remaining: float
    retry_after_seconds: float


class TokenBucket:
    def __init__(self, policy: RateLimitPolicy, *, clock: Callable[[], float] = time.monotonic) -> None:
        self.policy = policy
        self._clock = clock
        self._tokens = policy.capacity
        self._updated = clock()
        self._lock = threading.RLock()

    def _refill(self) -> None:
        now = self._clock()
        elapsed = max(0.0, now - self._updated)
        self._updated = now
        self._tokens = min(self.policy.capacity, self._tokens + elapsed * self.policy.refill_per_second)

    def acquire(self, cost: float | None = None) -> RateLimitDecision:
        charge = self.policy.cost_per_execution if cost is None else float(cost)
        if charge <= 0 or charge > self.policy.capacity:
            raise ValueError("invalid token-bucket charge")
        with self._lock:
            self._refill()
            if self._tokens >= charge:
                self._tokens -= charge
                return RateLimitDecision(True, self._tokens, 0.0)
            missing = charge - self._tokens
            retry = float("inf") if self.policy.refill_per_second == 0 else missing / self.policy.refill_per_second
            return RateLimitDecision(False, self._tokens, retry)

    def snapshot(self) -> float:
        with self._lock:
            self._refill()
            return self._tokens


class RateLimiter:
    """Bounded per-key token-bucket registry."""

    def __init__(
        self,
        policy: RateLimitPolicy | None = None,
        *,
        max_keys: int = 1024,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_keys <= 0:
            raise ValueError("max_keys must be positive")
        self.policy = policy or RateLimitPolicy()
        self.max_keys = max_keys
        self._clock = clock
        self._buckets: dict[str, TokenBucket] = {}
        self._lock = threading.RLock()

    def acquire(self, key: str, *, cost: float | None = None) -> RateLimitDecision:
        if not key or len(key) > 256:
            raise ValueError("rate-limit key must be non-empty and bounded")
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                if len(self._buckets) >= self.max_keys:
                    return RateLimitDecision(False, 0.0, float("inf"))
                bucket = TokenBucket(self.policy, clock=self._clock)
                self._buckets[key] = bucket
        return bucket.acquire(cost)

    def snapshot(self) -> dict[str, float]:
        with self._lock:
            return {key: bucket.snapshot() for key, bucket in self._buckets.items()}

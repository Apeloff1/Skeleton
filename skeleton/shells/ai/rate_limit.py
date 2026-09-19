"""Token-bucket rate limiting for model planning calls."""

from __future__ import annotations

from dataclasses import dataclass
import math
import threading
import time
from typing import Callable


@dataclass(frozen=True)
class AIModelRateLimit:
    capacity: float = 10.0
    refill_per_second: float = 1.0

    def __post_init__(self) -> None:
        if self.capacity <= 0 or self.refill_per_second <= 0:
            raise ValueError("model rate limits must be positive")


@dataclass(frozen=True)
class AIModelRateDecision:
    allowed: bool
    remaining: float
    retry_after_seconds: float

    def to_dict(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "remaining": self.remaining,
            "retry_after_seconds": self.retry_after_seconds,
        }


@dataclass
class _Bucket:
    tokens: float
    observed_at: float


class AIModelRateLimiter:
    def __init__(
        self,
        default: AIModelRateLimit | None = None,
        *,
        max_keys: int = 4096,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.default = default or AIModelRateLimit()
        self.max_keys = max_keys
        self._clock = clock
        self._buckets: dict[str, _Bucket] = {}
        self._overrides: dict[str, AIModelRateLimit] = {}
        self._lock = threading.RLock()

    def set_limit(self, key: str, limit: AIModelRateLimit) -> None:
        with self._lock:
            self._overrides[key] = limit
            self._buckets.pop(key, None)

    def _policy(self, key: str) -> AIModelRateLimit:
        return self._overrides.get(key, self.default)

    def inspect(self, key: str, *, cost: float = 1.0, consume: bool = False) -> AIModelRateDecision:
        if not key or len(key) > 256:
            raise ValueError("invalid model rate-limit key")
        if cost <= 0 or not math.isfinite(cost):
            raise ValueError("model call cost must be finite and positive")
        with self._lock:
            now = self._clock()
            policy = self._policy(key)
            bucket = self._buckets.get(key)
            if bucket is None:
                if len(self._buckets) >= self.max_keys:
                    raise RuntimeError("model rate-limit key capacity exhausted")
                bucket = _Bucket(policy.capacity, now)
                self._buckets[key] = bucket
            elapsed = max(0.0, now - bucket.observed_at)
            bucket.tokens = min(
                policy.capacity,
                bucket.tokens + elapsed * policy.refill_per_second,
            )
            bucket.observed_at = now
            allowed = bucket.tokens >= cost
            retry = 0.0 if allowed else (cost - bucket.tokens) / policy.refill_per_second
            if allowed and consume:
                bucket.tokens -= cost
            return AIModelRateDecision(
                allowed,
                max(0.0, bucket.tokens - (cost if allowed and not consume else 0.0)),
                max(0.0, retry),
            )

    def require(self, key: str, *, cost: float = 1.0) -> AIModelRateDecision:
        decision = self.inspect(key, cost=cost, consume=True)
        if not decision.allowed:
            raise RuntimeError(
                f"model planning rate limit exceeded; retry after {decision.retry_after_seconds:.3f}s"
            )
        return decision

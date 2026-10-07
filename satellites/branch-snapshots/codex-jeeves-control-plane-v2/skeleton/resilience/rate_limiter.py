"""Rate limiter — token-bucket and sliding-window rate limiting.

Provides per-key rate limiting with configurable refill rates and
burst capacity. Integrates with the resilience layer to protect
subsystems from overload.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class TokenBucket:
    capacity: float
    refill_rate: float
    tokens: float = 0.0
    last_refill_ns: int = 0

    def _refill(self) -> None:
        now = time.time_ns()
        elapsed = (now - self.last_refill_ns) / 1e9
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill_ns = now

    def consume(self, amount: float = 1.0) -> bool:
        self._refill()
        if self.tokens >= amount:
            self.tokens -= amount
            return True
        return False

    def wait_time_ms(self, amount: float = 1.0) -> float:
        self._refill()
        if self.tokens >= amount:
            return 0.0
        deficit = amount - self.tokens
        return (deficit / self.refill_rate) * 1000.0


class RateLimiter:
    """Token-bucket rate limiter with per-key tracking."""

    def __init__(self, default_capacity: float = 10.0, default_refill_rate: float = 1.0):
        self.default_capacity = default_capacity
        self.default_refill_rate = default_refill_rate
        self._buckets: Dict[str, TokenBucket] = {}

    def _bucket(self, key: str) -> TokenBucket:
        if key not in self._buckets:
            self._buckets[key] = TokenBucket(
                capacity=self.default_capacity,
                refill_rate=self.default_refill_rate,
                tokens=self.default_capacity,
                last_refill_ns=time.time_ns(),
            )
        return self._buckets[key]

    def allow(self, key: str, amount: float = 1.0) -> bool:
        return self._bucket(key).consume(amount)

    def wait_time(self, key: str, amount: float = 1.0) -> float:
        return self._bucket(key).wait_time_ms(amount)

    def set_rate(self, key: str, capacity: float, refill_rate: float) -> None:
        self._buckets[key] = TokenBucket(
            capacity=capacity,
            refill_rate=refill_rate,
            tokens=capacity,
            last_refill_ns=time.time_ns(),
        )

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "rate-limiter-card",
            "keys": len(self._buckets),
            "default_capacity": self.default_capacity,
            "default_refill_rate": self.default_refill_rate,
        }

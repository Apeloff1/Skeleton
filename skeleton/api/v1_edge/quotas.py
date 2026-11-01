"""Per-tenant token-bucket rate limits plus rolling-window quotas, keyed by quota class."""
from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple

from .envelope import EdgeError


@dataclass(frozen=True)
class QuotaPolicy:
    rate_per_s: float
    burst: int
    window_s: float = 86400.0
    window_limit: Optional[int] = None

    def __post_init__(self):
        if not (self.rate_per_s > 0 and math.isfinite(self.rate_per_s)):
            raise ValueError("rate_per_s must be positive and finite")
        if self.burst < 1:
            raise ValueError("burst must be >= 1")
        if self.window_limit is not None and self.window_limit < 1:
            raise ValueError("window_limit must be >= 1")


@dataclass
class _Bucket:
    tokens: float
    updated: float
    window_start: float
    window_used: int = 0


class TenantQuotas:
    def __init__(self, policies: Dict[str, QuotaPolicy], *,
                 overrides: Optional[Dict[Tuple[str, str], QuotaPolicy]] = None,
                 clock: Callable[[], float] = time.monotonic, max_buckets: int = 100_000):
        if "default" not in policies:
            raise ValueError("a 'default' quota class is required")
        self.policies = dict(policies)
        self.overrides = dict(overrides or {})
        self._clock = clock
        if type(max_buckets) is not int or max_buckets < 1:
            raise ValueError("max_buckets must be positive")
        self._buckets: Dict[Tuple[str, str], _Bucket] = {}
        self._max = max_buckets
        self._lock = threading.RLock()

    def policy_for(self, tenant: str, qclass: str) -> QuotaPolicy:
        return self.overrides.get((tenant, qclass)) or self.policies.get(qclass) or self.policies["default"]

    def check(self, tenant: str, qclass: str) -> Dict[str, str]:
        with self._lock:
            pol = self.policy_for(tenant, qclass)
            now = self._clock()
            key = (tenant, qclass)
            b = self._buckets.get(key)
            if b is None:
                if len(self._buckets) >= self._max:
                    self._evict(now)
                b = _Bucket(float(pol.burst), now, now)
                self._buckets[key] = b
            b.tokens = min(float(pol.burst), b.tokens + (now - b.updated) * pol.rate_per_s)
            b.updated = now
            if now - b.window_start >= pol.window_s:
                b.window_start, b.window_used = now, 0
            if pol.window_limit is not None and b.window_used >= pol.window_limit:
                reset = int(math.ceil(pol.window_s - (now - b.window_start)))
                raise EdgeError(429, "EDGE.QUOTA.EXHAUSTED", "quota exhausted",
                                {"quota_class": qclass}, {"retry-after": str(max(reset, 1))})
            if b.tokens < 1.0:
                wait = int(math.ceil((1.0 - b.tokens) / pol.rate_per_s))
                raise EdgeError(429, "EDGE.RATE.LIMITED", "rate limited",
                                {"quota_class": qclass}, {"retry-after": str(max(wait, 1))})
            b.tokens -= 1.0
            b.window_used += 1
            hdrs = {"ratelimit-limit": str(pol.burst), "ratelimit-remaining": str(int(b.tokens))}
            if pol.window_limit is not None:
                hdrs["x-quota-remaining"] = str(pol.window_limit - b.window_used)
            return hdrs

    def _evict(self, now: float) -> None:
        # Reclaim only buckets whose entire quota window and refill period elapsed.
        # Evicting a live tenant resets their limit and permits quota bypass.
        for key, bucket in tuple(self._buckets.items()):
            pol = self.policy_for(*key)
            safe_idle = max(pol.window_s, pol.burst / pol.rate_per_s)
            if now - bucket.updated >= safe_idle:
                del self._buckets[key]
        if len(self._buckets) >= self._max:
            raise EdgeError(503, "EDGE.QUOTA.CAPACITY", "quota state capacity exhausted")

    def usage(self, tenant: str) -> Dict[str, int]:
        with self._lock:
            return {q: b.window_used for (t, q), b in self._buckets.items() if t == tenant}

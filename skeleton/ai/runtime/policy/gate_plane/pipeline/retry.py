"""Retry specification and classification for the Pack F pipeline.

:class:`RetrySpec` is per-route policy: how many attempts, which failures
are retryable, and the exponential backoff schedule (with deterministic,
seedable jitter). Mutating requests are only retried when they carry an
``Idempotency-Key`` (Gate doctrine, same rule as
``gate_plane.proxy_contracts.RetryPolicy``) — PUT/DELETE count as
idempotent by HTTP semantics.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, FrozenSet, Optional, Tuple

from skeleton.gate_plane.pipeline.core import PipelineRequest, PipelineResponse
from skeleton.gate_plane.pipeline.errors import AttemptTimeout, BreakerOpenError, DeadlineExceeded, PipelineError

DEFAULT_RETRYABLE_STATUS: FrozenSet[int] = frozenset({502, 503, 504})


class Verdict(str, Enum):
    SUCCESS = "success"           # counts as breaker success, no retry
    CLIENT_ERROR = "client_error"  # 4xx: neither breaker failure nor retry
    RETRYABLE = "retryable"       # transient upstream failure: breaker failure + retry
    FATAL = "fatal"               # upstream failure that must not be retried


@dataclass(frozen=True)
class RetrySpec:
    max_attempts: int = 3
    base_backoff_s: float = 0.05
    max_backoff_s: float = 1.0
    multiplier: float = 2.0
    jitter: float = 0.2
    retryable_status: FrozenSet[int] = field(default=DEFAULT_RETRYABLE_STATUS)
    retry_on_429: bool = False
    honor_retry_after: bool = True
    max_retry_after_s: float = 5.0
    retry_unsafe_with_idempotency_key: bool = True

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.base_backoff_s < 0 or self.max_backoff_s < self.base_backoff_s:
            raise ValueError("need 0 <= base_backoff_s <= max_backoff_s")
        if self.multiplier < 1.0:
            raise ValueError("multiplier must be >= 1")
        if not 0.0 <= self.jitter <= 1.0:
            raise ValueError("jitter must be within [0, 1]")

    @classmethod
    def no_retry(cls) -> "RetrySpec":
        return cls(max_attempts=1)

    def backoff(self, retry_index: int, rng: Optional[random.Random] = None) -> float:
        """Delay before retry number ``retry_index`` (1-based), jittered ±``jitter``."""
        if retry_index < 1:
            return 0.0
        raw = min(self.max_backoff_s, self.base_backoff_s * (self.multiplier ** (retry_index - 1)))
        if self.jitter and raw > 0:
            r = (rng or random).random()
            raw = raw * (1.0 - self.jitter + 2.0 * self.jitter * r)
        return round(max(0.0, min(self.max_backoff_s, raw)), 6)

    def schedule(self, rng: Optional[random.Random] = None) -> Tuple[float, ...]:
        return tuple(self.backoff(i, rng) for i in range(1, self.max_attempts))

    def method_allows_retry(self, request: PipelineRequest) -> bool:
        if request.verb in ("GET", "HEAD", "OPTIONS", "PUT", "DELETE"):
            return True
        return self.retry_unsafe_with_idempotency_key and request.idempotency_key is not None

    def classify_response(self, response: PipelineResponse) -> Verdict:
        s = response.status
        if s < 400:
            return Verdict.SUCCESS
        if s == 429:
            return Verdict.RETRYABLE if self.retry_on_429 else Verdict.CLIENT_ERROR
        if s < 500:
            return Verdict.CLIENT_ERROR
        return Verdict.RETRYABLE if s in self.retryable_status else Verdict.FATAL

    @staticmethod
    def classify_error(exc: BaseException) -> Verdict:
        if isinstance(exc, BreakerOpenError):
            return Verdict.FATAL  # never hammer an open circuit
        if isinstance(exc, AttemptTimeout):
            return Verdict.RETRYABLE
        if isinstance(exc, DeadlineExceeded):
            return Verdict.FATAL  # total budget gone
        if isinstance(exc, PipelineError):
            return Verdict.FATAL
        if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
            return Verdict.RETRYABLE
        return Verdict.FATAL

    def retry_after_hint(self, response: PipelineResponse) -> Optional[float]:
        if not self.honor_retry_after:
            return None
        raw = response.header("retry-after")
        if raw is None:
            return None
        try:
            value = float(raw)
        except ValueError:
            return None
        if value < 0:
            return None
        return min(value, self.max_retry_after_s)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "max_attempts": self.max_attempts,
            "base_backoff_s": self.base_backoff_s,
            "max_backoff_s": self.max_backoff_s,
            "multiplier": self.multiplier,
            "jitter": self.jitter,
            "retryable_status": sorted(self.retryable_status),
            "retry_on_429": self.retry_on_429,
            "honor_retry_after": self.honor_retry_after,
            "max_retry_after_s": self.max_retry_after_s,
            "retry_unsafe_with_idempotency_key": self.retry_unsafe_with_idempotency_key,
        }


__all__ = ["DEFAULT_RETRYABLE_STATUS", "RetrySpec", "Verdict"]

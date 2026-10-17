"""Reconnect backoff: exponential with full jitter over the SDK ``RetryPolicy``.

ADR §4: base 0.5 s, cap 30 s, full jitter, reset after 60 s of a healthy
stream, and the server's SSE ``retry:`` value is honoured as a floor.
"""

from __future__ import annotations

import random
from typing import Callable, Optional

from ._compat import RetryPolicy

REALTIME_RETRY_POLICY = RetryPolicy(
    max_attempts=1_000,
    base_delay_seconds=0.5,
    max_delay_seconds=30.0,
)
HEALTHY_RESET_SECONDS = 60.0
_MAX_EXPONENT = 30  # 0.5 * 2**30 s is far past any cap; avoids float overflow


class ReconnectBackoff:
    """Stateful full-jitter delay generator."""

    def __init__(
        self,
        policy: Optional[RetryPolicy] = None,
        *,
        rng: Optional[Callable[[float, float], float]] = None,
        healthy_reset_s: float = HEALTHY_RESET_SECONDS,
    ) -> None:
        self.policy = policy or REALTIME_RETRY_POLICY
        self._uniform = rng or random.uniform
        self.healthy_reset_s = float(healthy_reset_s)
        self.attempt = 0
        self.retry_floor_s = 0.0

    @property
    def exhausted(self) -> bool:
        return self.attempt >= self.policy.max_attempts

    def honour_retry(self, retry_ms: Optional[int]) -> None:
        if retry_ms is not None and retry_ms >= 0:
            self.retry_floor_s = retry_ms / 1000.0

    def ceiling(self, attempt: Optional[int] = None) -> float:
        n = self.attempt if attempt is None else attempt
        return self.policy.delay_for_attempt(min(n, _MAX_EXPONENT))

    def next_delay(self) -> float:
        """Full jitter in ``[0, ceiling]``, floored by ``retry:``; advances attempt."""
        delay = self._uniform(0.0, self.ceiling())
        self.attempt += 1
        return max(self.retry_floor_s, float(delay))

    def note_healthy(self, healthy_for_s: float) -> None:
        if healthy_for_s >= self.healthy_reset_s:
            self.reset()

    def reset(self) -> None:
        self.attempt = 0


__all__ = ["HEALTHY_RESET_SECONDS", "REALTIME_RETRY_POLICY", "ReconnectBackoff"]

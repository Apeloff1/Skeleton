"""Bounded retry policy for idempotent GETs and safe retries."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Exponential backoff with a hard attempt cap."""

    max_attempts: int = 3
    base_delay_seconds: float = 0.1
    max_delay_seconds: float = 2.0
    retry_status_codes: frozenset[int] = frozenset({408, 429, 500, 502, 503, 504})

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.base_delay_seconds <= 0 or self.max_delay_seconds <= 0:
            raise ValueError("delays must be positive")
        if self.base_delay_seconds > self.max_delay_seconds:
            raise ValueError("base_delay cannot exceed max_delay")

    def delay_for_attempt(self, attempt: int) -> float:
        """Delay before retrying after a failed attempt (0-based)."""
        if attempt < 0:
            raise ValueError("attempt must be >= 0")
        delay = self.base_delay_seconds * (2**attempt)
        return min(delay, self.max_delay_seconds)

"""Deterministic retry policy for shell execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class RetryDecision:
    retry: bool
    delay_seconds: float
    reason: str


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 1
    initial_delay_seconds: float = 0.0
    multiplier: float = 2.0
    max_delay_seconds: float = 30.0
    retry_returncodes: frozenset[int] = frozenset()
    retry_timeouts: bool = False
    retry_output_limits: bool = False

    def __post_init__(self) -> None:
        if self.max_attempts <= 0:
            raise ValueError("max_attempts must be positive")
        if self.initial_delay_seconds < 0 or self.max_delay_seconds < 0:
            raise ValueError("retry delays must be non-negative")
        if self.multiplier < 1.0:
            raise ValueError("retry multiplier must be >= 1")
        object.__setattr__(self, "retry_returncodes", frozenset(self.retry_returncodes))

    @classmethod
    def none(cls) -> "RetryPolicy":
        return cls(max_attempts=1)

    @classmethod
    def transient_codes(
        cls,
        codes: Iterable[int],
        *,
        max_attempts: int = 3,
        initial_delay_seconds: float = 0.1,
        max_delay_seconds: float = 2.0,
    ) -> "RetryPolicy":
        return cls(
            max_attempts=max_attempts,
            initial_delay_seconds=initial_delay_seconds,
            max_delay_seconds=max_delay_seconds,
            retry_returncodes=frozenset(codes),
        )

    def delay_for_attempt(self, attempt: int) -> float:
        if attempt <= 0:
            raise ValueError("attempt must be positive")
        exponent = max(0, attempt - 1)
        delay = self.initial_delay_seconds * (self.multiplier**exponent)
        return min(delay, self.max_delay_seconds)

    def decide(
        self,
        *,
        attempt: int,
        returncode: int | None,
        timed_out: bool,
        output_limited: bool,
    ) -> RetryDecision:
        if attempt >= self.max_attempts:
            return RetryDecision(False, 0.0, "attempt limit reached")
        if timed_out:
            allowed = self.retry_timeouts
            reason = "timeout"
        elif output_limited:
            allowed = self.retry_output_limits
            reason = "output limit"
        elif returncode is not None and returncode in self.retry_returncodes:
            allowed = True
            reason = f"returncode {returncode}"
        else:
            allowed = False
            reason = "failure is not retryable"
        if not allowed:
            return RetryDecision(False, 0.0, reason)
        return RetryDecision(True, self.delay_for_attempt(attempt), reason)

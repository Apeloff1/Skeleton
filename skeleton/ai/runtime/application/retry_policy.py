"""Deterministic retry policy primitives for runtime execution.

Keeps retry decisions separate from command handlers and transports.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RetryDecision(str, Enum):
    RETRY = "retry"
    TERMINAL = "terminal"


@dataclass(frozen=True)
class RetryPolicy:
    """Bounded retry classification."""

    max_attempts: int = 3

    def decide(self, attempt: int, retryable: bool) -> RetryDecision:
        if retryable and attempt < self.max_attempts:
            return RetryDecision.RETRY
        return RetryDecision.TERMINAL

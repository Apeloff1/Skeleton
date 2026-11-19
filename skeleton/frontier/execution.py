"""Validated execution limits and portable failure categories."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


def positive_int(name: str, value: int, *, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def positive_seconds(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite positive number")
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a finite positive number")
    return float(value)


class ExecutionStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


class RuntimeBusy(RuntimeError):
    """The bounded admission queue is full or its waiting deadline expired."""


class RuntimeClosed(RuntimeError):
    """The runtime is draining or has shut down."""


class TransientAgentError(RuntimeError):
    """An adapter explicitly certifies that retrying this failure is safe."""


@dataclass(frozen=True, slots=True)
class ExecutionPolicy:
    max_concurrency: int = 8
    max_queue: int = 64
    execution_timeout: float = 30.0
    queue_timeout: float = 5.0
    max_payload_bytes: int = 1_048_576
    max_attempts: int = 1
    retry_delay: float = 0.05
    max_retry_delay: float = 1.0
    event_timeout: float = 0.1

    def __post_init__(self) -> None:
        for name in ("max_concurrency", "max_payload_bytes", "max_attempts"):
            positive_int(name, getattr(self, name))
        positive_int("max_queue", self.max_queue, minimum=0)
        for name in ("execution_timeout", "queue_timeout", "retry_delay", "max_retry_delay", "event_timeout"):
            positive_seconds(name, getattr(self, name))
        if self.max_attempts > 10:
            raise ValueError("max_attempts must be <= 10")
        if self.retry_delay > self.max_retry_delay:
            raise ValueError("retry_delay must not exceed max_retry_delay")

    def backoff(self, attempt: int) -> float:
        positive_int("attempt", attempt)
        return min(self.max_retry_delay, self.retry_delay * 2 ** min(attempt - 1, 30))

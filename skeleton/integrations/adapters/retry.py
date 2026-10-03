"""Retry policies with exponential backoff and jitter.

Three jitter strategies are supported (see the AWS architecture blog
"Exponential Backoff And Jitter"): ``none``, ``full`` and ``decorrelated``.
Retries only happen for errors whose ``retryable`` flag is set, never once
the caller's deadline would be exceeded by the next sleep, and never after
cancellation.  A provider's ``retry_after`` hint is honoured as a floor.
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Iterator, TypeVar

from .deadline import CancellationToken, Clock, Deadline, MonotonicClock
from .errors import (
    DeadlineExceededError,
    IntegrationError,
    OperationCancelledError,
    RateLimitedError,
    RetryExhaustedError,
    classify_exception,
)

__all__ = ["Jitter", "RetryPolicy", "RetryEvent", "retry_async", "NO_RETRY"]

T = TypeVar("T")


class Jitter(str, Enum):
    NONE = "none"
    FULL = "full"
    DECORRELATED = "decorrelated"


@dataclass(frozen=True)
class RetryEvent:
    attempt: int
    error: IntegrationError
    delay: float
    will_retry: bool


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay: float = 0.25
    max_delay: float = 8.0
    multiplier: float = 2.0
    jitter: Jitter = Jitter.FULL
    retry_on_codes: frozenset[str] = field(default_factory=frozenset)
    never_retry_codes: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not isinstance(self.max_attempts, int) or self.max_attempts < 1:
            raise ValueError("max_attempts must be an integer >= 1")
        if self.base_delay < 0 or self.max_delay < 0:
            raise ValueError("delays must be non-negative")
        if self.max_delay < self.base_delay:
            raise ValueError("max_delay must be >= base_delay")
        if self.multiplier < 1.0:
            raise ValueError("multiplier must be >= 1")
        object.__setattr__(self, "jitter", Jitter(self.jitter))
        object.__setattr__(self, "retry_on_codes", frozenset(self.retry_on_codes))
        object.__setattr__(self, "never_retry_codes", frozenset(self.never_retry_codes))

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RetryPolicy":
        known = {"max_attempts", "base_delay", "max_delay", "multiplier", "jitter"}
        unknown = set(payload) - known - {"retry_on_codes", "never_retry_codes"}
        if unknown:
            raise ValueError(f"unknown retry policy keys: {sorted(unknown)}")
        kwargs: dict[str, Any] = {k: payload[k] for k in known if k in payload}
        if "retry_on_codes" in payload:
            kwargs["retry_on_codes"] = frozenset(payload["retry_on_codes"])
        if "never_retry_codes" in payload:
            kwargs["never_retry_codes"] = frozenset(payload["never_retry_codes"])
        return cls(**kwargs)

    def should_retry(self, error: IntegrationError) -> bool:
        if isinstance(error, OperationCancelledError):
            return False
        if error.code in self.never_retry_codes:
            return False
        if error.code in self.retry_on_codes:
            return True
        return bool(error.retryable)

    def delays(self, rng: random.Random | None = None) -> Iterator[float]:
        """Yield the sleep before attempt 2, 3, ... (``max_attempts - 1`` values)."""

        rnd = rng or random.Random()
        previous = self.base_delay
        for retry_index in range(self.max_attempts - 1):
            ceiling = min(self.max_delay, self.base_delay * (self.multiplier**retry_index))
            if self.jitter is Jitter.NONE:
                delay = ceiling
            elif self.jitter is Jitter.FULL:
                delay = rnd.uniform(0.0, ceiling)
            else:
                upper = max(self.base_delay, previous * 3.0)
                delay = min(self.max_delay, rnd.uniform(self.base_delay, upper))
            previous = delay
            yield delay


NO_RETRY = RetryPolicy(max_attempts=1, base_delay=0.0, max_delay=0.0)


async def retry_async(
    operation: Callable[[int], Awaitable[T]],
    *,
    policy: RetryPolicy,
    clock: Clock | None = None,
    deadline: Deadline | None = None,
    token: CancellationToken | None = None,
    rng: random.Random | None = None,
    on_event: Callable[[RetryEvent], None] | None = None,
    provider: str | None = None,
) -> tuple[T, int]:
    """Run ``operation(attempt)`` until success; return ``(result, attempts)``.

    Raises the original error if it is not retryable, or
    :class:`RetryExhaustedError` once all attempts fail.  Deadline and
    cancellation are checked before every attempt and before every sleep.
    """

    clk = clock or MonotonicClock()
    delays = policy.delays(rng)
    attempt = 0
    while True:
        attempt += 1
        if token is not None:
            token.check()
        if deadline is not None:
            deadline.check("retry loop")
        try:
            return await operation(attempt), attempt
        except BaseException as raw:  # noqa: BLE001 - classified below
            if isinstance(raw, (KeyboardInterrupt, SystemExit, asyncio.CancelledError)):
                raise
            error = classify_exception(raw, provider=provider)
            if isinstance(error, OperationCancelledError):
                raise error from raw
            retry = policy.should_retry(error) and attempt < policy.max_attempts
            delay = next(delays, None) if retry else None
            if delay is not None and isinstance(error, RateLimitedError) and error.retry_after is not None:
                delay = max(delay, min(error.retry_after, policy.max_delay))
            if retry and delay is not None and deadline is not None and delay >= deadline.remaining():
                retry = False
            if on_event is not None:
                on_event(RetryEvent(attempt, error, delay or 0.0, bool(retry and delay is not None)))
            if not retry or delay is None:
                if attempt == 1 or not policy.should_retry(error):
                    if error is raw:
                        raise
                    raise error from raw
                if isinstance(error, DeadlineExceededError) and deadline is not None and deadline.expired():
                    raise error from raw
                raise RetryExhaustedError(
                    f"gave up after {attempt} attempts: {error.message}",
                    attempts=attempt,
                    last_error=error,
                    provider=provider,
                    retryable=False,
                ) from raw
            if token is not None:
                token.check()
            await clk.sleep(delay)

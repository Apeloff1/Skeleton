"""Tests for retry policies, jitter strategies and the async retry loop."""

from __future__ import annotations

import asyncio
import random

import pytest

from .deadline import CancellationToken, Deadline, ManualClock
from .errors import (
    AuthenticationError,
    DeadlineExceededError,
    InvalidRequestError,
    OperationCancelledError,
    ProviderUnavailableError,
    RateLimitedError,
    RetryExhaustedError,
)
from .retry import NO_RETRY, Jitter, RetryEvent, RetryPolicy, retry_async


def test_policy_validation():
    with pytest.raises(ValueError):
        RetryPolicy(max_attempts=0)
    with pytest.raises(ValueError):
        RetryPolicy(base_delay=-1)
    with pytest.raises(ValueError):
        RetryPolicy(base_delay=2, max_delay=1)
    with pytest.raises(ValueError):
        RetryPolicy(multiplier=0.5)


def test_from_dict_and_unknown_keys():
    pol = RetryPolicy.from_dict({"max_attempts": 4, "jitter": "none", "retry_on_codes": ["x"]})
    assert pol.max_attempts == 4 and pol.jitter is Jitter.NONE and "x" in pol.retry_on_codes
    with pytest.raises(ValueError):
        RetryPolicy.from_dict({"attempts": 3})


def test_exponential_delays_without_jitter_are_capped():
    pol = RetryPolicy(max_attempts=6, base_delay=1, max_delay=5, multiplier=2, jitter=Jitter.NONE)
    assert list(pol.delays()) == [1, 2, 4, 5, 5]


def test_full_jitter_bounded_and_deterministic_with_seed():
    pol = RetryPolicy(max_attempts=5, base_delay=1, max_delay=8, jitter=Jitter.FULL)
    a = list(pol.delays(random.Random(42)))
    b = list(pol.delays(random.Random(42)))
    assert a == b
    ceilings = [1, 2, 4, 8]
    assert all(0 <= d <= c for d, c in zip(a, ceilings))


def test_decorrelated_jitter_within_bounds():
    pol = RetryPolicy(max_attempts=20, base_delay=0.5, max_delay=4, jitter=Jitter.DECORRELATED)
    delays = list(pol.delays(random.Random(1)))
    assert len(delays) == 19
    assert all(0.5 <= d <= 4 for d in delays)


def test_should_retry_codes():
    pol = RetryPolicy(retry_on_codes=frozenset({"invalid_request"}), never_retry_codes=frozenset({"rate_limited"}))
    assert pol.should_retry(InvalidRequestError())
    assert not pol.should_retry(RateLimitedError())
    assert pol.should_retry(ProviderUnavailableError())
    assert not pol.should_retry(OperationCancelledError())


def _flaky(failures: list[BaseException], value: str = "ok"):
    calls: list[int] = []

    async def op(attempt: int) -> str:
        calls.append(attempt)
        if failures:
            raise failures.pop(0)
        return value

    return op, calls


def test_retry_succeeds_after_transient_failures():
    clock = ManualClock()
    op, calls = _flaky([ProviderUnavailableError(), ConnectionResetError()])
    events: list[RetryEvent] = []
    pol = RetryPolicy(max_attempts=3, base_delay=1, max_delay=4, jitter=Jitter.NONE)
    result, attempts = asyncio.run(retry_async(op, policy=pol, clock=clock, on_event=events.append))
    assert (result, attempts) == ("ok", 3)
    assert calls == [1, 2, 3]
    assert clock.sleeps == [1, 2]
    assert [e.will_retry for e in events] == [True, True]


def test_non_retryable_error_raised_immediately():
    op, calls = _flaky([AuthenticationError("nope")])
    with pytest.raises(AuthenticationError):
        asyncio.run(retry_async(op, policy=RetryPolicy(max_attempts=5), clock=ManualClock()))
    assert calls == [1]


def test_exhaustion_wraps_last_error():
    op, calls = _flaky([ProviderUnavailableError("a"), ProviderUnavailableError("b"), ProviderUnavailableError("c")])
    pol = RetryPolicy(max_attempts=3, base_delay=0.1, max_delay=0.1, jitter=Jitter.NONE)
    with pytest.raises(RetryExhaustedError) as info:
        asyncio.run(retry_async(op, policy=pol, clock=ManualClock(), provider="p"))
    assert info.value.attempts == 3
    assert info.value.last_error.message == "c"
    assert info.value.provider == "p"


def test_single_attempt_policy_reraises_original():
    op, _ = _flaky([ProviderUnavailableError("down")])
    with pytest.raises(ProviderUnavailableError):
        asyncio.run(retry_async(op, policy=NO_RETRY, clock=ManualClock()))


def test_retry_after_hint_is_a_floor():
    clock = ManualClock()
    op, _ = _flaky([RateLimitedError(retry_after=3.0)])
    pol = RetryPolicy(max_attempts=2, base_delay=0.1, max_delay=10, jitter=Jitter.NONE)
    asyncio.run(retry_async(op, policy=pol, clock=clock))
    assert clock.sleeps == [3.0]


def test_retry_stops_when_sleep_would_cross_deadline():
    clock = ManualClock()
    dl = Deadline.after(1.0, clock)
    op, calls = _flaky([ProviderUnavailableError(), ProviderUnavailableError()])
    pol = RetryPolicy(max_attempts=3, base_delay=2, max_delay=2, jitter=Jitter.NONE)
    with pytest.raises(ProviderUnavailableError):
        asyncio.run(retry_async(op, policy=pol, clock=clock, deadline=dl))
    assert calls == [1]
    assert clock.sleeps == []


def test_retry_respects_expired_deadline_before_attempt():
    clock = ManualClock()
    dl = Deadline.after(0.5, clock)
    clock.advance(1)
    op, calls = _flaky([])
    with pytest.raises(DeadlineExceededError):
        asyncio.run(retry_async(op, policy=RetryPolicy(), clock=clock, deadline=dl))
    assert calls == []


def test_cancellation_stops_retry_loop():
    token = CancellationToken()

    async def op(attempt: int) -> str:
        token.cancel("stop")
        raise ProviderUnavailableError()

    with pytest.raises(OperationCancelledError):
        asyncio.run(retry_async(op, policy=RetryPolicy(max_attempts=5), clock=ManualClock(), token=token))


def test_asyncio_cancellation_is_not_swallowed():
    async def op(attempt: int) -> str:
        raise asyncio.CancelledError()

    async def main() -> None:
        await retry_async(op, policy=RetryPolicy(max_attempts=3), clock=ManualClock())

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(main())


def test_unknown_exceptions_are_not_retried():
    op, calls = _flaky([RuntimeError("bug")])
    with pytest.raises(Exception) as info:
        asyncio.run(retry_async(op, policy=RetryPolicy(max_attempts=4), clock=ManualClock()))
    assert calls == [1]
    assert info.value.code == "provider_error"  # type: ignore[attr-defined]

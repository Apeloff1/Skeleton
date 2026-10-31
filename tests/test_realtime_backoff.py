"""Reconnect backoff: full jitter over RetryPolicy, retry floor, healthy reset."""

from __future__ import annotations

import pytest

from skeleton.client.realtime._compat import RetryPolicy, SkeletonClientError
from skeleton.client.realtime.backoff import REALTIME_RETRY_POLICY, ReconnectBackoff
from skeleton.client.realtime.errors import RealtimeAuthError, RealtimeError


def test_policy_matches_adr_defaults():
    assert REALTIME_RETRY_POLICY.base_delay_seconds == 0.5
    assert REALTIME_RETRY_POLICY.max_delay_seconds == 30.0
    assert REALTIME_RETRY_POLICY.delay_for_attempt(0) == 0.5
    assert REALTIME_RETRY_POLICY.delay_for_attempt(20) == 30.0


def test_full_jitter_is_uniform_between_zero_and_ceiling():
    seen = []
    backoff = ReconnectBackoff(rng=lambda lo, hi: seen.append((lo, hi)) or hi)
    delays = [backoff.next_delay() for _ in range(8)]
    assert seen[0] == (0.0, 0.5)
    assert delays == [0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0]
    assert all(lo == 0.0 for lo, _ in seen)


def test_random_jitter_stays_in_bounds():
    backoff = ReconnectBackoff()
    for attempt in range(40):
        ceiling = backoff.ceiling()
        delay = backoff.next_delay()
        assert 0.0 <= delay <= ceiling <= 30.0, attempt


def test_retry_field_is_a_floor():
    backoff = ReconnectBackoff(rng=lambda lo, hi: lo)
    backoff.honour_retry(2000)
    assert backoff.next_delay() == 2.0


def test_resets_after_sixty_seconds_healthy():
    backoff = ReconnectBackoff(rng=lambda lo, hi: hi)
    for _ in range(5):
        backoff.next_delay()
    backoff.note_healthy(59.0)
    assert backoff.attempt == 5
    backoff.note_healthy(60.0)
    assert backoff.attempt == 0


def test_exhaustion_follows_max_attempts():
    backoff = ReconnectBackoff(RetryPolicy(max_attempts=2, base_delay_seconds=0.5, max_delay_seconds=30.0))
    backoff.next_delay()
    assert not backoff.exhausted
    backoff.next_delay()
    assert backoff.exhausted


def test_huge_attempt_counts_do_not_overflow():
    backoff = ReconnectBackoff(rng=lambda lo, hi: hi)
    backoff.attempt = 5000
    assert backoff.next_delay() == 30.0


def test_errors_subclass_sdk_base():
    assert issubclass(RealtimeError, SkeletonClientError)
    assert issubclass(RealtimeAuthError, SkeletonClientError)
    with pytest.raises(ValueError):
        RetryPolicy(max_attempts=0)

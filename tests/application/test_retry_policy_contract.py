"""Regression tests for deterministic retry decisions."""

from skeleton.application.retry_policy import RetryPolicy


def test_retry_policy_stops_after_limit():
    policy = RetryPolicy(max_attempts=2)

    assert policy.should_retry(attempt=1) is True
    assert policy.should_retry(attempt=2) is False


def test_retry_policy_rejects_negative_attempts():
    policy = RetryPolicy(max_attempts=2)

    assert policy.should_retry(attempt=-1) is False

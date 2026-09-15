"""Numeric fail-closed regressions for API rate limiting."""

import math

import pytest

import api_middleware
from api_middleware import RateLimiterMiddleware


@pytest.mark.parametrize(
    "kwargs",
    [
        {"per_minute": math.inf},
        {"per_minute": -math.inf},
        {"per_minute": math.nan},
        {"burst": math.inf},
        {"burst": -math.inf},
        {"burst": math.nan},
        {"max_buckets": math.inf},
        {"max_buckets": -math.inf},
        {"max_buckets": math.nan},
        {"bucket_ttl": math.inf},
        {"bucket_ttl": -math.inf},
        {"bucket_ttl": math.nan},
    ],
)
def test_rate_limiter_rejects_nonfinite_runtime_configuration(kwargs) -> None:
    with pytest.raises(ValueError, match="positive finite"):
        RateLimiterMiddleware(object(), **kwargs)


def test_retry_after_is_bounded_for_extreme_finite_values() -> None:
    assert api_middleware._bounded_retry_after(0.0) == 1
    assert api_middleware._bounded_retry_after(0.000001) == 1
    assert api_middleware._bounded_retry_after(86_400.0) == 86_400
    assert api_middleware._bounded_retry_after(10**300) == 86_400


def test_retry_after_fails_closed_for_nonfinite_values() -> None:
    assert api_middleware._bounded_retry_after(math.inf) == 86_400
    assert api_middleware._bounded_retry_after(-math.inf) == 86_400
    assert api_middleware._bounded_retry_after(math.nan) == 86_400

import math

import pytest

from skeleton.agents.swarm_rate_limit import TokenBucketLimiter


def test_refund_restores_consumed_capacity_without_overflow() -> None:
    limiter = TokenBucketLimiter(capacity=3, refill_per_second=1e-9, clock=lambda: 0.0)
    assert limiter.allow("tenant", cost=2) is True
    assert limiter.remaining("tenant") == pytest.approx(1.0)
    assert limiter.refund("tenant", cost=2) == pytest.approx(3.0)
    assert limiter.refund("tenant", cost=2) == pytest.approx(3.0)


def test_refund_rejects_non_positive_cost() -> None:
    limiter = TokenBucketLimiter(capacity=1, refill_per_second=1, clock=lambda: 0.0)
    with pytest.raises(ValueError, match="cost must be a positive finite number"):
        limiter.refund("tenant", cost=0)


def test_refund_normalizes_and_validates_key() -> None:
    limiter = TokenBucketLimiter(capacity=2, refill_per_second=1e-9, clock=lambda: 0.0)
    assert limiter.allow(" tenant ", cost=1) is True
    assert limiter.refund("tenant", cost=1) == pytest.approx(2.0)
    with pytest.raises(ValueError, match="rate-limit key must not be empty"):
        limiter.refund("   ", cost=1)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_constructor_rejects_non_finite_capacity(value: float) -> None:
    with pytest.raises(ValueError, match="capacity must be a positive finite number"):
        TokenBucketLimiter(capacity=value, refill_per_second=1)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_constructor_rejects_non_finite_refill(value: float) -> None:
    with pytest.raises(ValueError, match="refill_per_second must be a positive finite number"):
        TokenBucketLimiter(capacity=1, refill_per_second=value)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_allow_rejects_non_finite_cost_without_poisoning_bucket(value: float) -> None:
    limiter = TokenBucketLimiter(capacity=2, refill_per_second=1e-9, clock=lambda: 0.0)
    with pytest.raises(ValueError, match="cost must be a positive finite number"):
        limiter.allow("tenant", cost=value)
    assert limiter.remaining("tenant") == pytest.approx(2.0)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_refund_rejects_non_finite_cost_without_poisoning_bucket(value: float) -> None:
    limiter = TokenBucketLimiter(capacity=2, refill_per_second=1e-9, clock=lambda: 0.0)
    assert limiter.allow("tenant") is True
    with pytest.raises(ValueError, match="cost must be a positive finite number"):
        limiter.refund("tenant", cost=value)
    assert limiter.remaining("tenant") == pytest.approx(1.0)

"""A non-positive epsilon must not mint privacy budget or crash the noise draw."""

import random

import pytest

from skeleton.memory.dp import ExponentialMechanism, LaplaceMechanism, PrivacyAccountant, SeededNoise


class _Zero(random.Random):
    def random(self) -> float:
        return 0.0


def test_negative_epsilon_does_not_increase_the_budget() -> None:
    accountant = PrivacyAccountant(session_budget=1.0)
    assert accountant.spend(-0.4, "laplace", "count") is False
    assert accountant.remaining() == 1.0
    mechanism = LaplaceMechanism(accountant)
    assert mechanism.privatize_count(4, 0.0, "q") is None
    assert accountant.remaining() == 1.0


def test_inverted_mean_range_does_not_spend() -> None:
    accountant = PrivacyAccountant(session_budget=1.0)
    mechanism = LaplaceMechanism(accountant)
    with pytest.raises(ValueError):
        mechanism.privatize_mean([1.0], 0.2, "mean", (1.0, 0.0))
    assert accountant.remaining() == 1.0


def test_laplace_survives_a_zero_draw() -> None:
    drawn = SeededNoise.laplace(_Zero(), 1.0)
    assert drawn == 0.0 or abs(drawn) > 0.0
    assert drawn == drawn  # not NaN


def test_non_positive_sensitivity_does_not_spend() -> None:
    accountant = PrivacyAccountant(session_budget=1.0)
    mechanism = ExponentialMechanism(accountant)
    with pytest.raises(ValueError):
        mechanism.select({"a": 1.0, "b": 0.0}, 0.2, "pick", sensitivity=0.0)
    assert accountant.remaining() == 1.0

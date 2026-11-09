"""Holt smoothing rejects a bad setup instead of forecasting garbage."""

import math

import pytest

from skeleton.intelligence.forecaster import Forecaster


def test_steps_and_parameters_are_bounded() -> None:
    with pytest.raises(ValueError):
        Forecaster(alpha=0.0)
    with pytest.raises(ValueError):
        Forecaster(damping=-0.2)
    caster = Forecaster()
    with pytest.raises(ValueError):
        caster.feed("queue", math.nan)
    caster.feed("queue", 1.0)
    caster.feed("queue", 2.0)
    caster.feed("queue", 3.0)
    with pytest.raises(ValueError):
        caster.forecast("queue", steps=0)
    assert caster.forecast("queue", steps=1)["forecast"][0]["step"] == 1

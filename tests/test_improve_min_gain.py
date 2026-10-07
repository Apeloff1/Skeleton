"""A negative min_gain must not count a worse score as an improvement."""

import pytest

from skeleton.intelligence.improve_loop import ImproveLoop


def test_negative_min_gain_is_rejected() -> None:
    with pytest.raises(ValueError):
        ImproveLoop(min_gain=-0.1)


def test_equal_score_is_not_an_improvement() -> None:
    loop = ImproveLoop(max_iterations=2, patience=2, min_gain=0.0)
    result = loop.run(1, lambda incumbent, i: incumbent, lambda value: float(value))
    assert result.best == 1
    assert all(not step.improved for step in result.iterations)

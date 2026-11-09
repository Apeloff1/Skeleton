"""A NaN loss must not poison the bandit, and log(0) is not a score."""

import math

import pytest

from skeleton.intelligence.adaptive import AdaptiveLearner, Arm


def test_nan_loss_is_rejected_and_zero_total_does_not_crash() -> None:
    learner = AdaptiveLearner([{"lr": 0.1}])
    with pytest.raises(ValueError):
        learner.report({"lr": 0.1}, final_loss=math.nan, wall_time_s=0.1)
    assert Arm(config={"lr": 0.1}, pulls=1, total_reward=1.0).ucb1(0) == float("inf")

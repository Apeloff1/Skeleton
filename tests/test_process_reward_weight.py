"""A recency weight above 1 would make the oldest step count the most."""

import pytest

from skeleton.intelligence.process_reward import StepScore, Trajectory


def test_recency_weight_must_stay_in_unit_interval() -> None:
    trajectory = Trajectory(scores=[StepScore(0, 0.0, 0.0), StepScore(1, 1.0, 1.0)])
    with pytest.raises(ValueError):
        trajectory.aggregate(recency_weight=-1.0)
    with pytest.raises(ValueError):
        trajectory.aggregate(recency_weight=1.5)
    assert trajectory.aggregate(recency_weight=0.0) == 1.0

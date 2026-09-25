"""An arm that has not been pulled has no mean reward."""

import pytest

from skeleton.intelligence.adaptive import AdaptiveLearner


def test_untried_mean_is_not_zero() -> None:
    learner = AdaptiveLearner([{"lr": 0.1}, {"lr": 0.01}])
    assert learner.stats()["best_mean_reward"] is None
    assert next(iter(learner._arms.values())).mean_reward is None
    with pytest.raises(ValueError):
        learner.report({"lr": 9}, final_loss=0.2, wall_time_s=0.1)
    with pytest.raises(ValueError):
        learner.report({"lr": 0.1}, final_loss=0.2, wall_time_s=-1)
    learner.report({"lr": 0.1}, final_loss=0.0, wall_time_s=0.1, failed=False)
    assert learner.stats()["best_mean_reward"] == 1.0

"""Tests for adaptive learning and the meta-arm grid."""

from skeleton.intelligence import AdaptiveLearner, default_meta_grid


class TestAdaptive:
    def test_grid_nonempty(self):
        grid = default_meta_grid()
        assert grid

    def test_learner_constructs(self):
        learner = AdaptiveLearner(default_meta_grid())
        assert learner is not None

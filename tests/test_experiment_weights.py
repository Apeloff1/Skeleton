"""Experiment weights have to cover every variant and stay non-negative."""

import pytest

from skeleton.intelligence.experiment_tracker import ExperimentTracker


def test_weight_list_must_match_variants() -> None:
    tracker = ExperimentTracker()
    with pytest.raises(ValueError):
        tracker.create("exp", variants=["a", "b"], weights=[1])
    with pytest.raises(ValueError):
        tracker.create("exp", variants=["a", "b"], weights=[0, 0])
    tracker.create("exp", variants=["a", "b"], weights=[1, 3])
    assert tracker.assign("exp", "subject") in {"a", "b"}

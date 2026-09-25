"""An empty variant has no mean, and an unknown variant does not swallow the outcome."""

import pytest

from skeleton.intelligence.experiment_tracker import ExperimentTracker


def test_empty_mean_and_unknown_variant() -> None:
    with pytest.raises(ValueError):
        ExperimentTracker(significance_level=True)
    tracker = ExperimentTracker()
    tracker.create("exp", variants=["control", "treatment"])
    card = tracker.card()["experiments"]["exp"]["variants"]["control"]
    assert card["mean"] is None
    assert tracker._experiments["exp"].variants["control"].std() is None
    with pytest.raises(ValueError):
        tracker.record("exp", "missing", 1.0)
    with pytest.raises(ValueError):
        tracker.record("exp", "control", True)
    with pytest.raises(KeyError):
        tracker.assign("missing", "subject")
    tracker.record("exp", "control", 1.0)
    assert tracker._experiments["exp"].variants["control"].mean() == 1.0

import pytest

from skeleton.frontier.gameforge_health_score import HealthScore


def test_health_score_rejects_boolean_window():
    with pytest.raises(ValueError):
        HealthScore(True)


def test_health_score_rejects_non_boolean_sample():
    score = HealthScore(2)
    with pytest.raises(TypeError):
        score.record(1)


def test_health_score_tracks_boolean_samples():
    score = HealthScore(2)
    assert score.record(True) == 1.0
    assert score.record(False) == 0.5
    assert score.sample_count == 2

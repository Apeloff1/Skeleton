from skeleton.frontier.gameforge_health_score import HealthScore


def test_health_score_tracks_bounded_samples():
    score = HealthScore(2)
    assert score.sample_count == 0
    assert score.healthy
    score.record(False)
    assert score.sample_count == 1
    assert score.degraded
    score.record(True)
    assert score.sample_count == 2
    assert score.value == 0.5
    score.record(True)
    assert score.sample_count == 2
    assert score.value == 1.0

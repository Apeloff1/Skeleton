from skeleton.frontier.worldsim.navigation import NavGrid
from skeleton.frontier.worldsim.quality_arena import (WorldCandidate, pacing_score,
    encounter_spacing_score, score_paced)


def test_pacing_prefers_rising_with_relief():
    good = [0.1, 0.3, 0.2, 0.5, 0.4, 0.7, 0.6, 1.0]
    flat = [0.5] * 8
    assert pacing_score(good) > pacing_score(flat)
    assert pacing_score([1.0, 0.1, 0.1, 0.1]) < pacing_score(good)


def test_encounter_spacing():
    assert encounter_spacing_score([0, 4, 8, 12], 2, 8) == 1.0
    assert encounter_spacing_score([0, 0.5, 1, 30], 2, 8) == 0.0


def test_score_paced_flags_failures():
    c = WorldCandidate("w", NavGrid.from_rows(["..."]), (0, 0), ((2, 0),), ("a", "b"), 1.0)
    ok = score_paced(c, 10, [0.1, 0.3, 0.2, 0.6, 0.5, 1.0], [0, 4, 8])
    bad = score_paced(c, 10, [0.5] * 6, [0, 0.1, 0.2])
    assert ok.passed and ok.total > bad.total
    assert set(bad.failures) == {"flat_pacing", "encounter_spacing"}

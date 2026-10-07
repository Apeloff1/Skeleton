"""An empty heuristic reading is not a score of zero."""

import pytest

from skeleton.jeeves.planning.heuristics import HEURISTICS, aggregate, rank


def test_missing_heuristics_are_refused() -> None:
    with pytest.raises(ValueError):
        aggregate({})
    with pytest.raises(ValueError):
        HEURISTICS[0].score(101)
    with pytest.raises(ValueError):
        HEURISTICS[0].score(True)
    complete = {item.name: 0.0 for item in HEURISTICS}
    assert aggregate(complete) == 0.0
    topped = {item.name: 100.0 for item in HEURISTICS}
    scored = dict(rank(topped))
    assert scored[HEURISTICS[0].name] == pytest.approx(HEURISTICS[0].weight)

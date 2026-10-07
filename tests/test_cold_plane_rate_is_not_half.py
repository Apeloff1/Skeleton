"""A plane with no trials has no win rate, and a partial weight map is not complete."""

import pytest

from skeleton.retrieval.plane_weights import PlaneWeightLearner


def test_cold_rate_and_partial_weights() -> None:
    learner = PlaneWeightLearner()
    assert learner.stats()["rates"]["rag"] is None
    with pytest.raises(ValueError):
        PlaneWeightLearner({"rag": 1.0})
    full = {plane: 1.0 for plane in ("rag", "cag", "mag", "kag")}
    full["rag"] = 1.4
    learned = PlaneWeightLearner(full)
    learned._arms["rag"].wins = 3
    learned._arms["rag"].trials = 4
    assert learned.stats()["rates"]["rag"] == 0.75
    assert learned._arms["rag"].weight == 1.4

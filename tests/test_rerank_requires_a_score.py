"""A result with no score is not given one half."""

import pytest

from skeleton.retrieval.reranker import FeatureReranker


def test_a_missing_score_is_not_invented() -> None:
    ranker = FeatureReranker()
    with pytest.raises(ValueError):
        ranker.rerank("heat", [{"id": "a", "text": "heat vent"}])
    with pytest.raises(ValueError):
        ranker.rerank("heat", [{"id": "a", "text": "heat vent", "score": True}])
    with pytest.raises(ValueError):
        ranker.rerank("", [{"id": "a", "text": "heat vent", "score": 0.2}])
    hits = ranker.rerank("heat", [{"id": "a", "text": "heat vent", "score": 0.2}])
    assert hits[0].item_id == "a"
    assert hits[0].score != 0.5

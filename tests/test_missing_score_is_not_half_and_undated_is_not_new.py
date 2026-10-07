"""A result with no score is not half relevant, and an undated result is not new."""

import pytest

from skeleton.retrieval.ranking import Ranker


class _Hit:
    def __init__(self, fragment_id, content, score=None, metadata=None):
        self.fragment_id = fragment_id
        self.content = content
        if score is not None:
            self.score = score
        if metadata is not None:
            self.metadata = metadata


def test_missing_score_and_undated_result() -> None:
    with pytest.raises(ValueError):
        Ranker(recency_weight=True)
    with pytest.raises(ValueError):
        Ranker().rank([_Hit("bare", "text")])
    now = 1_700_000_000.0
    ranked = Ranker(recency_weight=0.2, diversity_weight=0.0).rank([
        _Hit("undated", "alpha", score=0.4),
        _Hit("dated", "beta", score=0.4, metadata={"timestamp": now}),
    ])
    assert [item.fragment_id for item in ranked] == ["dated", "undated"]

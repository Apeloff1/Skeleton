"""Diversity credit follows score order, and top_k=0 does not mean everything."""

import pytest

from skeleton.retrieval.fusion import ScoredResult
from skeleton.retrieval.ranking import Ranker


def _item(fragment_id: str, content: str, score: float) -> ScoredResult:
    return ScoredResult(
        fragment_id=fragment_id,
        content=content,
        score=score,
        metadata={"timestamp": 10**12},
    )


def test_stronger_duplicate_keeps_the_diversity_bonus() -> None:
    ranked = Ranker().rank([
        _item("weak", "same text", 0.50),
        _item("strong", "same text", 0.55),
        _item("other", "different text", 0.52),
    ])
    assert [item.fragment_id for item in ranked] == ["strong", "other", "weak"]


def test_top_k_zero_returns_nothing_and_negative_is_rejected() -> None:
    items = [_item("a", "alpha", 0.2)]
    assert Ranker().rank(items, top_k=0) == []
    with pytest.raises(ValueError):
        Ranker().rank(items, top_k=-1)

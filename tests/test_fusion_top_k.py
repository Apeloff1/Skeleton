"""A negative fusion limit must not return the tail of the ranking."""

import pytest

from skeleton.retrieval.fusion import Fuser, ScoredResult


def test_negative_top_k_is_rejected() -> None:
    results = {
        "rag": [ScoredResult("a", "alpha", 0.9), ScoredResult("b", "beta", 0.1)],
    }
    with pytest.raises(ValueError):
        Fuser().fuse(results, top_k=-1)
    assert Fuser().fuse(results, top_k=0) == []

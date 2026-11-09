"""A rerank limit of zero must not return every boosted hit."""

import pytest

from skeleton.retrieval.fusion import ScoredResult
from skeleton.retrieval.rerank import Reranker


def test_top_k_zero_is_empty_and_negative_is_rejected() -> None:
    items = [ScoredResult("a", "alpha", 0.4), ScoredResult("b", "beta", 0.9)]
    assert Reranker().rerank(items, top_k=0) == ()
    with pytest.raises(ValueError):
        Reranker().rerank(items, top_k=-1)


def test_rerank_does_not_share_metadata() -> None:
    item = ScoredResult("a", "alpha", 0.4, metadata={"preview": "alpha"})
    ranked = Reranker().rerank([item])
    ranked[0].metadata["preview"] = "changed"
    assert item.metadata["preview"] == "alpha"

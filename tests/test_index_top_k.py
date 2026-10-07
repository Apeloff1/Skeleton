"""A negative index limit must not return the weakest hits."""

import pytest

from skeleton.retrieval.index import InvertedIndex


def test_negative_top_k_is_rejected() -> None:
    index = InvertedIndex()
    index.add("a", "alpha beta")
    index.add("b", "alpha")
    with pytest.raises(ValueError):
        index.search("alpha", top_k=-1)
    assert index.search("alpha", top_k=0) == ()


def test_bm25_parameters_are_bounded() -> None:
    with pytest.raises(ValueError):
        InvertedIndex(k1=-0.1)
    with pytest.raises(ValueError):
        InvertedIndex(b=1.5)

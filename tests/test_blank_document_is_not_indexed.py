"""A blank document is not in the index, and a blank query is not zero hits."""

import pytest

from skeleton.retrieval.index import InvertedIndex


def test_blank_text_and_blank_query_raise() -> None:
    index = InvertedIndex()
    with pytest.raises(ValueError):
        index.add("empty", "   ")
    with pytest.raises(ValueError):
        index.search("   ")
    index.add("a", "alpha beta")
    assert index.search("alpha", top_k=0) == ()
    assert index.search("alpha")[0].fragment_id == "a"

"""An empty query is not a medium-length document."""

import pytest

from skeleton.retrieval.reranker import FeatureExtractor


def test_empty_query_has_no_length_ratio() -> None:
    with pytest.raises(ValueError):
        FeatureExtractor.extract("   ", "a document with several words here")
    with pytest.raises(ValueError):
        FeatureExtractor.extract("query", None)  # type: ignore[arg-type]
    features = FeatureExtractor.extract("query", "")
    assert features["length_ratio"] == 0.0
    assert features["term_overlap"] == 0.0
    matched = FeatureExtractor.extract("query", "query")
    assert matched["term_overlap"] == 1.0
    assert matched["length_ratio"] == pytest.approx(0.2)

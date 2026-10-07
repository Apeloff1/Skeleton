"""A plane hit with no score is not a zero-score result."""

import pytest

from skeleton.retrieval.quad import QuadRetriever
from skeleton.retrieval.fusion import ScoredResult


class _Chunk:
    chunk_id = "chunk-1"
    text = "body"
    metadata = {"source": "memory"}


class _Hit:
    def __init__(self, score=None):
        self.chunk = _Chunk()
        if score is not None:
            self.score = score


def test_missing_plane_score_raises() -> None:
    with pytest.raises(ValueError):
        QuadRetriever._normalize_result("rag", _Hit())
    with pytest.raises(ValueError):
        QuadRetriever._normalize_result("rag", {"id": "doc", "text": "body"})
    with pytest.raises(ValueError):
        QuadRetriever._normalize_result("rag", _Hit(True))
    normalized = QuadRetriever._normalize_result("rag", _Hit(0.4))
    assert isinstance(normalized, ScoredResult)
    assert normalized.score == 0.4
    assert normalized.fragment_id == "chunk-1"

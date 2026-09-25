"""A result with no score is not the weakest duplicate."""

import pytest

from skeleton.retrieval.dedup import Deduper
from skeleton.retrieval.fusion import ScoredResult


def test_missing_score_and_missing_id_raise() -> None:
    with pytest.raises(ValueError):
        Deduper().dedupe([ScoredResult(fragment_id="doc", content="alpha", score=True, plane="rag")])
    bare = ScoredResult(fragment_id="doc", content="alpha", score=0.2, plane="rag")
    del bare.score
    with pytest.raises(ValueError):
        Deduper().dedupe([bare])
    nameless = ScoredResult(fragment_id="", content="alpha", score=0.2, plane="rag")
    with pytest.raises(ValueError):
        Deduper().dedupe([nameless])

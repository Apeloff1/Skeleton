"""Deduper must understand ScoredResult, not a field the fusion contract never had."""

import pytest

from skeleton.retrieval.dedup import Deduper
from skeleton.retrieval.fusion import ScoredResult


def _hit(fragment_id: str, content: str, score: float) -> ScoredResult:
    return ScoredResult(fragment_id=fragment_id, content=content, score=score, plane="rag")


def test_dedupe_keeps_higher_score_for_the_same_fragment() -> None:
    kept = Deduper().dedupe([
        _hit("doc", "alpha", 0.2),
        _hit("doc", "alpha revised", 0.9),
    ])
    assert [item.score for item in kept] == [0.9]


def test_dedupe_collapses_the_same_content_prefix() -> None:
    kept = Deduper(signature_length=8).dedupe([
        _hit("a", "shared-prefix-one", 0.4),
        _hit("b", "shared-prefix-two", 0.8),
        _hit("c", "different", 0.1),
    ])
    assert [item.fragment_id for item in kept] == ["b", "c"]


def test_signature_length_must_be_positive() -> None:
    with pytest.raises(ValueError):
        Deduper(signature_length=0)

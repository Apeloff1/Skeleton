"""Labyrinthine content scrutiny engine tests."""
from skeleton.ai.runtime.learning_foundation.content_retrieval import ContentScrutinyEngine
from skeleton.ai.runtime.learning_foundation.multimodal import MultimodalCorpus

def test_scrutiny_nested_bounds_and_summary():
    engine = ContentScrutinyEngine(max_depth=4)
    corpus = MultimodalCorpus()
    evidence = engine.scrutinize(corpus)
    assert evidence.bounds_ok
    assert len(evidence.digests) >= 3
    summary = engine.summary()
    assert summary["n_evidence"] >= 1
    assert summary["all_bounds_ok"] is True
    assert summary["max_depth_seen"] >= 0

import pytest

from skeleton.ai.runtime.learning_foundation.content_retrieval import (
    ContentScrutinyError,
    ScrutinyEvidence,
)


@pytest.mark.parametrize("depth", [-1, 9, True, 3.25])
def test_scrutiny_rejects_invalid_constructor_depth(depth):
    with pytest.raises(ContentScrutinyError, match="max_depth"):
        ContentScrutinyEngine(max_depth=depth)


def test_scrutiny_requires_typed_corpus_and_bound_depth():
    engine = ContentScrutinyEngine(max_depth=2)
    with pytest.raises(ContentScrutinyError, match="typed corpus"):
        engine.scrutinize(object())
    with pytest.raises(ContentScrutinyError, match="max scrutiny depth"):
        engine.scrutinize(MultimodalCorpus(), depth=3)
    assert engine.summary()["total_evidence"] == 0


def test_scrutiny_issues_digest_sealed_four_layer_receipt():
    engine = ContentScrutinyEngine(max_depth=1)
    result = engine.scrutinize(MultimodalCorpus(), depth=1)
    assert isinstance(result, ScrutinyEvidence)
    assert result.layers == ("bounds", "digest", "authority", "temporal")
    assert len(result.digests) == 4
    assert all(len(digest) == 64 for digest in result.digests)
    assert result.bounds_ok is True
    assert result.recursion_depth == 1
    assert engine.summary()["n_evidence"] == 1


def test_scrutiny_evidence_rejects_fake_bounds_authority():
    with pytest.raises(ContentScrutinyError, match="failed bounds"):
        ScrutinyEvidence(
            ("bounds", "digest", "authority", "temporal"),
            ("0" * 64,) * 4,
            False,
            0,
            1.0,
        )

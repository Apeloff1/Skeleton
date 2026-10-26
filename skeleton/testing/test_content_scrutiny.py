"""Regression coverage for bounded, read-only multimodal content scrutiny."""

import pytest

from skeleton.ai.runtime.learning_foundation.content_retrieval import (
    ContentScrutinyEngine,
    ContentScrutinyError,
    ScrutinyEvidence,
)
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


@pytest.mark.parametrize("depth", [-1, 1, True, 0.5, None])
def test_scrutiny_rejects_noncanonical_requested_depth(depth):
    engine = ContentScrutinyEngine(max_depth=0)
    with pytest.raises(ContentScrutinyError, match="max scrutiny depth"):
        engine.scrutinize(MultimodalCorpus(), depth=depth)
    assert engine.summary()["total_evidence"] == 0


def test_scrutiny_retained_receipts_are_bounded():
    engine = ContentScrutinyEngine(max_depth=0)
    corpus = MultimodalCorpus()
    for _ in range(130):
        assert engine.scrutinize(corpus).bounds_ok
    summary = engine.summary()
    assert summary["total_evidence"] == 130
    assert summary["n_evidence"] == 128
    assert summary["retained_evidence_limit"] == 128
    assert summary["max_depth_seen"] == 0


@pytest.mark.parametrize("depth,timestamp,error", [
    (-1, 1.0, "depth"),
    (9, 1.0, "depth"),
    (True, 1.0, "depth"),
    (0, 0.0, "timestamp"),
    (0, float("nan"), "timestamp"),
    (0, True, "timestamp"),
])
def test_scrutiny_receipt_rejects_invalid_depth_or_time(depth, timestamp, error):
    with pytest.raises(ContentScrutinyError, match=error):
        ScrutinyEvidence(
            ("bounds", "digest", "authority", "temporal"),
            ("0" * 64,) * 4,
            True,
            depth,
            timestamp,
        )


def test_corrupt_corpus_never_issues_positive_scrutiny_receipt():
    corpus = MultimodalCorpus()
    corpus._records["orphaned"] = object()
    engine = ContentScrutinyEngine()
    with pytest.raises(ContentScrutinyError, match="verification failed"):
        engine.scrutinize(corpus)
    assert engine.summary()["total_evidence"] == 0

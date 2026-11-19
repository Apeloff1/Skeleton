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

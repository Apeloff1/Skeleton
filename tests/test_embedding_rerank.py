"""Embedding rerank must use the fusion result fields, not item_id/source."""

import pytest

from skeleton.retrieval.embeddings import LocalEmbedder, rerank_by_embedding
from skeleton.retrieval.fusion import ScoredResult


def test_rerank_by_embedding_uses_content_and_keeps_identity() -> None:
    embedder = LocalEmbedder(dim=32)
    items = [
        ScoredResult("far", "unrelated quarry stone", 0.9, metadata={"text": "quarry stone"}),
        ScoredResult("near", "alpha beta alpha", 0.1, metadata={"text": "alpha beta"}),
    ]
    ranked = rerank_by_embedding(embedder, "alpha beta", items, weight=0.8)
    assert ranked[0].fragment_id == "near"
    assert ranked[0].content == "alpha beta alpha"
    assert ranked[0].plane == "rag"
    ranked[0].metadata["text"] = "mutated"
    assert items[1].metadata["text"] == "alpha beta"


def test_similarity_rejects_mismatched_dimensions() -> None:
    with pytest.raises(ValueError):
        LocalEmbedder().similarity((1.0, 0.0), (1.0,))


def test_rerank_weight_must_stay_inside_the_unit_interval() -> None:
    item = ScoredResult("a", "alpha", 0.5)
    with pytest.raises(ValueError):
        rerank_by_embedding(LocalEmbedder(dim=8), "alpha", [item], weight=1.5)

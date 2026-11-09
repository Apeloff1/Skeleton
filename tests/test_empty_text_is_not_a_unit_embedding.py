"""Empty text is not a unit embedding, and a result id is not substitute text."""

import pytest

from skeleton.retrieval.embeddings import LocalEmbedder, rerank_by_embedding
from skeleton.retrieval.fusion import ScoredResult


def test_empty_text_and_missing_result_text_raise() -> None:
    with pytest.raises(ValueError):
        LocalEmbedder(dim=True)
    embedder = LocalEmbedder(dim=16)
    with pytest.raises(ValueError):
        embedder.vector("   ")
    with pytest.raises(ValueError):
        embedder.vector("...")
    vector = embedder.vector("alpha")
    assert abs(sum(value * value for value in vector) - 1.0) < 1e-9
    with pytest.raises(ValueError):
        rerank_by_embedding(embedder, "alpha", [ScoredResult("id-only", "   ", 0.4)])

"""A zero embedding is not a unit vector, and it does not score one half."""

import math

import pytest

from skeleton.memory.core import Chunk
from skeleton.memory.vector import HashEmbedder, VectorStore


def test_zero_embedding_is_rejected() -> None:
    with pytest.raises(ValueError):
        HashEmbedder().embed("a")
    vector = HashEmbedder().embed("alpha beta")
    assert math.sqrt(sum(value * value for value in vector)) == pytest.approx(1.0)
    with pytest.raises(ValueError):
        VectorStore(embedder=lambda text: [0.0, 0.0]).add(Chunk(text="alpha", chunk_id="a"))
    store = VectorStore(embedder=lambda text: [3.0, 0.0])
    store.add(Chunk(text="alpha", chunk_id="a"))
    assert store.query("alpha")[0].score == pytest.approx(1.0)

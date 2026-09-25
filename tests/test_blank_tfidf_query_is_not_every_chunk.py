"""A blank query is not a match for every chunk, and a zero cosine is not a hit."""

import pytest

from skeleton.memory.rag import InMemoryTFIDFStore
from skeleton.memory.types import MemoryChunk


def _chunk(chunk_id: str, text: str) -> MemoryChunk:
    return MemoryChunk(id=chunk_id, text=text, metadata={}, source_tier="rag")


def test_blank_query_and_unrelated_chunk() -> None:
    store = InMemoryTFIDFStore()
    with pytest.raises(ValueError):
        store.add(_chunk("empty", " "))
    store.add(_chunk("alpha", "alpha beta"))
    with pytest.raises(ValueError):
        store.query("   ")
    assert store.query("zzzz") == []
    assert [row.chunk.id for row in store.query("alpha")] == ["alpha"]

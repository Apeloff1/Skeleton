"""An episode that shares no words with the query is not a hit."""

import pytest

from skeleton.memory.mag import MAGStore
from skeleton.memory.types import MemoryChunk


def test_blank_and_unrelated_queries() -> None:
    store = MAGStore("user-a")
    store.add(MemoryChunk(id="c", text="alpha beta", metadata={}))
    with pytest.raises(ValueError):
        store.query("   ")
    assert store.query("zzzz") == []
    hits = store.query("alpha")
    assert hits[0].chunk.metadata["importance"] == 0.0
    assert "alpha" in hits[0].chunk.text

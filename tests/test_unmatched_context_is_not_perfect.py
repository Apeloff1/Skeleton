"""An unmatched persona query is not a perfect context hit."""

import pytest

from skeleton.kernel.errors import RagQueryError
from skeleton.memory.cag import CAGStore
from skeleton.memory.types import MemoryChunk


def test_unmatched_query_and_wrong_persona_raise() -> None:
    store = CAGStore()
    with pytest.raises(RagQueryError):
        store.query("alpha")
    store.create_persona("tutor", "Jeeves", "You are a patient tutor.")
    store.add(MemoryChunk(id="c1", text="Recursion is a function calling itself.", metadata={"topic": "alpha"}))
    assert store.query("recursion") == []
    hit = store.query("alpha")
    assert hit[0].score == pytest.approx(1.0)
    assert hit[0].chunk.confidence == pytest.approx(1.0)
    with pytest.raises(ValueError):
        store.query_scoped("alpha", scope={"persona_id": "other"})

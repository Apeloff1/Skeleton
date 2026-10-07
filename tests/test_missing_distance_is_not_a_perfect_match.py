"""A hit with no distance is not a perfect match."""

import pytest

from skeleton.memory.rag import ChromaDBStore, RagQueryError


class _Collection:
    def __init__(self, payload):
        self.payload = payload

    def query(self, **kwargs):
        return self.payload


def _store(payload) -> ChromaDBStore:
    store = ChromaDBStore.__new__(ChromaDBStore)
    store._available = True
    store._collection = _Collection(payload)
    return store


def test_missing_distance_is_rejected() -> None:
    store = _store({
        "ids": [["m1"]],
        "documents": [["alpha"]],
        "metadatas": [[{"topic": "alpha"}]],
    })
    with pytest.raises(RagQueryError):
        store.query("alpha")
    with pytest.raises(ValueError):
        store.query("alpha", top_k=True)
    complete = _store({
        "ids": [["m1"]],
        "documents": [["alpha"]],
        "metadatas": [[{"topic": "alpha"}]],
        "distances": [[0.25]],
    })
    hits = complete.query("alpha")
    assert hits[0].score == pytest.approx(0.75)

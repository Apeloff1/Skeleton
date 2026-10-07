"""Backing memory stores must preserve replacement, deletion, and ordering invariants."""

import pytest

from skeleton.memory.cag import CAGStore
from skeleton.memory.mag import MAGStore
from skeleton.memory.rag import InMemoryTFIDFStore
from skeleton.memory.types import MemoryChunk


def _chunk(
    chunk_id: str,
    text: str,
    *,
    tenant: str = "A",
    topic: str = "topic",
) -> MemoryChunk:
    return MemoryChunk(
        id=chunk_id,
        text=text,
        metadata={"tenant_id": tenant, "topic": topic},
        source_tier="rag",
    )


def test_tfidf_replacement_does_not_double_count_documents_or_terms() -> None:
    store = InMemoryTFIDFStore()
    store.add(_chunk("doc", "alpha beta"))
    store.add(_chunk("doc", "gamma"))

    assert store.health()["chunks"] == 1
    assert store._total_docs == 1
    assert "alpha" not in store._doc_freq
    assert "beta" not in store._doc_freq
    assert store._doc_freq["gamma"] == 1
    assert [row.chunk.id for row in store.query("gamma")] == ["doc"]


def test_tfidf_delete_after_replacement_leaves_clean_accounting() -> None:
    store = InMemoryTFIDFStore()
    store.add(_chunk("doc", "alpha"))
    store.add(_chunk("doc", "beta"))
    assert store.delete("doc") is True

    assert store._total_docs == 0
    assert store._doc_freq == {}
    assert store.health()["chunks"] == 0


def test_tfidf_equal_score_order_is_deterministic_by_chunk_id() -> None:
    store = InMemoryTFIDFStore()
    store.add(_chunk("z", "alpha"))
    store.add(_chunk("a", "alpha"))

    assert [row.chunk.id for row in store.query("alpha", top_k=2)] == ["a", "z"]


@pytest.mark.parametrize("top_k", [-1, True, 1.5])
def test_tfidf_rejects_invalid_limits(top_k) -> None:
    store = InMemoryTFIDFStore()
    store.add(_chunk("a", "alpha"))
    with pytest.raises((TypeError, ValueError)):
        store.query("alpha", top_k=top_k)


def test_cag_delete_repairs_current_token_accounting() -> None:
    store = CAGStore()
    persona = store.create_persona("p", "P", "system")
    store.add(
        MemoryChunk(
            id="node",
            text="abcd" * 20,
            metadata={"topic": "node"},
            source_tier="cag",
        )
    )
    before = persona.current_tokens
    assert before > 0

    assert store.delete("node") is True

    assert persona.current_tokens < before
    assert "node" not in persona.knowledge_graph
    assert "node" not in persona.importance_scores


def test_cag_zero_limit_returns_no_context() -> None:
    store = CAGStore()
    store.create_persona("p", "P", "system")
    assert store.query("anything", top_k=0) == []


def test_mag_readding_same_content_replaces_old_tag_membership() -> None:
    store = MAGStore("u")
    episode_id = store.add_episode("same content", tags={"old"})
    same_id = store.add_episode("same content", tags={"new"})

    assert same_id == episode_id
    assert episode_id not in store._tag_index.get("old", set())
    assert store._tag_index["new"] == {episode_id}


def test_mag_delete_removes_empty_tag_bucket() -> None:
    store = MAGStore("u")
    episode_id = store.add_episode("alpha", tags={"single"})
    assert store.delete(episode_id) is True
    assert "single" not in store._tag_index


@pytest.mark.parametrize(
    ("kwargs", "error"),
    (
        ({"content": ""}, ValueError),
        ({"content": "x", "emotional_valence": 2.0}, ValueError),
        ({"content": "x", "importance": -1.0}, ValueError),
        ({"content": "x", "tags": ["not-a-set"]}, TypeError),
    ),
)
def test_mag_rejects_invalid_episode_state(kwargs, error) -> None:
    store = MAGStore("u")
    with pytest.raises(error):
        store.add_episode(**kwargs)


def test_mag_equal_score_order_is_stable() -> None:
    store = MAGStore("u")
    first = store.add_episode("alpha one", importance=1.0)
    second = store.add_episode("alpha two", importance=1.0)
    # Freeze the same temporal/access state to force a score tie.
    store._episodes[first].timestamp = 10.0
    store._episodes[second].timestamp = 10.0
    store._episodes[first].last_accessed = 10.0
    store._episodes[second].last_accessed = 10.0

    rows = store.query("alpha", top_k=2)
    assert [row.chunk.id for row in rows] == sorted([first, second])

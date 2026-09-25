"""Authorization/data scope must be enforced before retrieval ranking."""

import pytest

from skeleton.memory.mag import MAGStore
from skeleton.memory.rag import InMemoryTFIDFStore
from skeleton.memory.types import MemoryChunk
from skeleton.retrieval.fusion import ScoredResult
from skeleton.retrieval.quad import QuadRetriever
from skeleton.retrieval.scope import RetrievalScope, ScopedRetrievalError


def test_scope_digest_is_canonical_and_does_not_expose_values() -> None:
    left = RetrievalScope.from_mapping({"tenant_id": "A", "project": "P"})
    right = RetrievalScope.from_mapping({"project": "P", "tenant_id": "A"})
    assert left.digest == right.digest
    assert "tenant_id" not in left.digest
    assert "A" not in left.digest


def test_scoped_rag_filters_metadata_before_scoring() -> None:
    store = InMemoryTFIDFStore()
    store.add(
        MemoryChunk(
            id="tenant-a",
            text="alpha alpha alpha",
            metadata={"tenant_id": "A"},
            source_tier="rag",
        )
    )
    store.add(
        MemoryChunk(
            id="tenant-b",
            text="alpha alpha alpha alpha",
            metadata={"tenant_id": "B"},
            source_tier="rag",
        )
    )
    quad = QuadRetriever()
    quad.register_plane("rag", store)

    results, receipt = quad.retrieve_scoped_with_receipt(
        "alpha",
        {"tenant_id": "A"},
        use_cache=False,
    )

    assert [item.fragment_id for item in results] == ["tenant-a"]
    assert receipt.scope_digest == RetrievalScope.from_mapping(
        {"tenant_id": "A"}
    ).digest
    assert results[0].metadata["fusion_planes"] == ("rag",)


def test_scope_is_part_of_cache_identity() -> None:
    store = InMemoryTFIDFStore()
    store.add(MemoryChunk("a", "alpha", {"tenant_id": "A"}, source_tier="rag"))
    store.add(MemoryChunk("b", "alpha", {"tenant_id": "B"}, source_tier="rag"))
    quad = QuadRetriever()
    quad.register_plane("rag", store)

    a = quad.retrieve_scoped("alpha", {"tenant_id": "A"})
    b = quad.retrieve_scoped("alpha", {"tenant_id": "B"})

    assert [item.fragment_id for item in a] == ["a"]
    assert [item.fragment_id for item in b] == ["b"]


def test_scoped_retrieval_refuses_plane_without_pre_rank_enforcement() -> None:
    calls = []

    class UnsafePlane:
        def query(self, query: str, top_k: int):
            calls.append(query)
            return [ScoredResult("secret", "secret", 1.0)]

    quad = QuadRetriever()
    quad.register_plane("rag", UnsafePlane())

    with pytest.raises(ScopedRetrievalError, match="lack query_scoped"):
        quad.retrieve_scoped("secret", {"tenant_id": "A"})
    assert calls == []


def test_scoped_retrieval_aborts_if_scoped_plane_fails() -> None:
    class BrokenScopedPlane:
        def query_scoped(self, query: str, top_k: int, scope):
            raise RuntimeError("scope backend unavailable")

    quad = QuadRetriever()
    quad.register_plane("rag", BrokenScopedPlane())

    with pytest.raises(ScopedRetrievalError, match="plane.s. failed"):
        quad.retrieve_scoped("alpha", {"tenant_id": "A"}, use_cache=False)
    assert quad.stats()["plane_failures"] == 1


def test_mag_user_scope_is_identity_bound() -> None:
    store = MAGStore("user-a")
    store.add_episode("alpha memory", importance=1.0)

    assert store.query_scoped(
        "alpha",
        top_k=3,
        scope={"user_id": "user-b"},
    ) == []
    assert store.query_scoped(
        "alpha",
        top_k=3,
        scope={"user_id": "user-a"},
    )


def test_scope_contract_rejects_empty_or_duplicate_boundaries() -> None:
    with pytest.raises(ValueError):
        RetrievalScope.from_mapping({})
    with pytest.raises(ValueError):
        RetrievalScope((("tenant_id", "A"), ("tenant_id", "B")))

from __future__ import annotations

import math

import pytest

from skeleton.memory.rag import InMemoryTFIDFStore as CanonicalStore
from skeleton.ai.runtime.memory.rag import InMemoryTFIDFStore as AIStore
from skeleton.memory.types import MemoryChunk as CanonicalChunk
from skeleton.ai.runtime.memory.types import MemoryChunk as AIChunk


def _exercise(store_type,chunk_type):
    store=store_type()
    metadata={"tenant_id":"tenant-a","nested":{"labels":["safe"]}}
    embedding=[0.1,0.2]
    chunk=chunk_type(
        id="doc-1",
        text="alpha governed memory",
        metadata=metadata,
        embedding=embedding,
        source_tier="rag",
    )
    store.add(chunk)
    return store,metadata,embedding


def test_rag_admission_isolated_from_original_metadata_mutation() -> None:
    for store_type,chunk_type in (
        (CanonicalStore,CanonicalChunk),
        (AIStore,AIChunk),
    ):
        store,metadata,_=_exercise(store_type,chunk_type)
        metadata["tenant_id"]="tenant-b"
        metadata["nested"]["labels"].append("mutated")

        allowed=store.query_scoped(
            "alpha",
            scope={"tenant_id":"tenant-a"},
        )
        denied=store.query_scoped(
            "alpha",
            scope={"tenant_id":"tenant-b"},
        )

        assert [item.chunk.id for item in allowed]==["doc-1"]
        assert denied==[]
        assert allowed[0].chunk.metadata["nested"]["labels"]==["safe"]


def test_rag_query_result_mutation_cannot_rewrite_stored_scope() -> None:
    for store_type,chunk_type in (
        (CanonicalStore,CanonicalChunk),
        (AIStore,AIChunk),
    ):
        store,_,_=_exercise(store_type,chunk_type)
        first=store.query_scoped(
            "alpha",
            scope={"tenant_id":"tenant-a"},
        )[0]
        first.chunk.metadata["tenant_id"]="tenant-b"
        first.chunk.metadata["nested"]["labels"].append("escaped")
        assert first.chunk.embedding is not None
        first.chunk.embedding.append(999.0)

        second=store.query_scoped(
            "alpha",
            scope={"tenant_id":"tenant-a"},
        )[0]

        assert second.chunk.metadata["tenant_id"]=="tenant-a"
        assert second.chunk.metadata["nested"]["labels"]==["safe"]
        assert second.chunk.embedding==[0.1,0.2]


def test_rag_admission_copies_embedding_vector() -> None:
    for store_type,chunk_type in (
        (CanonicalStore,CanonicalChunk),
        (AIStore,AIChunk),
    ):
        store,_,embedding=_exercise(store_type,chunk_type)
        embedding[0]=42.0

        result=store.query("alpha")[0]
        assert result.chunk.embedding==[0.1,0.2]


def test_rag_admission_rejects_boolean_embedding_values() -> None:
    for store_type,chunk_type in (
        (CanonicalStore,CanonicalChunk),
        (AIStore,AIChunk),
    ):
        store=store_type()
        chunk=chunk_type(
            id="doc-bool",
            text="alpha governed memory",
            metadata={"tenant_id":"tenant-a"},
            embedding=[0.1,True],
            source_tier="rag",
        )
        with pytest.raises(TypeError,match="embedding values must be numeric"):
            store.add(chunk)


def test_rag_admission_rejects_non_finite_mutable_fields() -> None:
    for store_type,chunk_type in (
        (CanonicalStore,CanonicalChunk),
        (AIStore,AIChunk),
    ):
        for field,value,match in (
            ("embedding",[0.1,math.inf],"embedding values must be finite"),
            ("timestamp",math.nan,"timestamp must be finite numeric data"),
            ("confidence",math.inf,"confidence must be finite numeric data"),
        ):
            kwargs={
                "id":"doc-invalid",
                "text":"alpha governed memory",
                "metadata":{"tenant_id":"tenant-a"},
                "embedding":[0.1,0.2],
                "source_tier":"rag",
            }
            kwargs[field]=value
            chunk=chunk_type(**kwargs)
            with pytest.raises(ValueError,match=match):
                store.add(chunk)


def test_rag_admission_rejects_non_string_identity_without_coercion() -> None:
    for store_type,chunk_type in (
        (CanonicalStore,CanonicalChunk),
        (AIStore,AIChunk),
    ):
        store=store_type()
        chunk=chunk_type(
            id=7,
            text="alpha governed memory",
            metadata={"tenant_id":"tenant-a"},
            source_tier="rag",
        )
        with pytest.raises(ValueError,match="id must be a non-empty string"):
            store.add(chunk)

from __future__ import annotations

import pytest

from skeleton.memory.core import Chunk as CanonicalChunk
from skeleton.memory.vector import HashEmbedder as CanonicalHashEmbedder
from skeleton.memory.vector import VectorStore as CanonicalVectorStore
from skeleton.ai.runtime.memory.vector import HashEmbedder as AIHashEmbedder
from skeleton.ai.runtime.memory.vector import VectorStore as AIVectorStore


@pytest.mark.parametrize("embedder_type",[CanonicalHashEmbedder,AIHashEmbedder])
def test_hash_embedder_requires_positive_dimension(embedder_type) -> None:
    with pytest.raises(ValueError,match="dims must be a positive integer"):
        embedder_type(0)
    with pytest.raises(ValueError,match="dims must be a positive integer"):
        embedder_type(True)


@pytest.mark.parametrize("store_type",[CanonicalVectorStore,AIVectorStore])
def test_vector_store_rejects_document_dimension_drift(store_type) -> None:
    calls=0
    def embed(text:str)->list[float]:
        nonlocal calls
        calls+=1
        return [1.0,0.0] if calls==1 else [1.0,0.0,0.0]

    store=store_type(embedder=embed)
    store.add(CanonicalChunk(text="alpha",chunk_id="a"))

    with pytest.raises(ValueError,match="embedding dimension drift"):
        store.add(CanonicalChunk(text="beta",chunk_id="b"))

    assert store.stats()["documents"]==1
    assert store.stats()["dimensions"]==2


@pytest.mark.parametrize("store_type",[CanonicalVectorStore,AIVectorStore])
def test_vector_store_rejects_query_dimension_drift(store_type) -> None:
    mode={"query":False}
    def embed(text:str)->list[float]:
        return [1.0,0.0,0.0] if mode["query"] else [1.0,0.0]

    store=store_type(embedder=embed)
    store.add(CanonicalChunk(text="alpha",chunk_id="a"))
    mode["query"]=True

    with pytest.raises(ValueError,match="embedding dimension drift"):
        store.query("alpha")


@pytest.mark.parametrize("store_type",[CanonicalVectorStore,AIVectorStore])
def test_vector_store_rejects_negative_or_boolean_top_k(store_type) -> None:
    store=store_type(dims=8)
    store.add(CanonicalChunk(text="alpha beta",chunk_id="a"))

    with pytest.raises(ValueError,match="top_k"):
        store.query("alpha",top_k=-1)
    with pytest.raises(ValueError,match="top_k"):
        store.query_many(["alpha"],top_k=True)


@pytest.mark.parametrize("store_type",[CanonicalVectorStore,AIVectorStore])
def test_zero_top_k_remains_empty_and_dimension_safe(store_type) -> None:
    store=store_type(dims=8)
    store.add(CanonicalChunk(text="alpha beta",chunk_id="a"))

    assert store.query("alpha",top_k=0)==[]
    assert store.query_many(["alpha","beta"],top_k=0)==[[],[]]


@pytest.mark.parametrize("store_type",[CanonicalVectorStore,AIVectorStore])
def test_vector_store_rejects_threshold_query_dimension_drift(store_type) -> None:
    mode={"query":False}
    def embed(text:str)->list[float]:
        return [1.0,0.0,0.0] if mode["query"] else [1.0,0.0]

    store=store_type(embedder=embed)
    store.add(CanonicalChunk(text="alpha",chunk_id="a"))
    mode["query"]=True

    with pytest.raises(ValueError,match="embedding dimension drift"):
        store.query_threshold("alpha",minimum_score=0.0)


@pytest.mark.parametrize("store_type",[CanonicalVectorStore,AIVectorStore])
def test_vector_store_rejects_threshold_batch_dimension_drift(store_type) -> None:
    mode={"query":False}
    def embed(text:str)->list[float]:
        return [1.0,0.0,0.0] if mode["query"] else [1.0,0.0]

    store=store_type(embedder=embed)
    store.add(CanonicalChunk(text="alpha",chunk_id="a"))
    mode["query"]=True

    with pytest.raises(ValueError,match="embedding dimension drift"):
        store.query_threshold_many(["alpha"],minimum_score=0.0)


@pytest.mark.parametrize("store_type",[CanonicalVectorStore,AIVectorStore])
def test_zero_top_k_skips_query_embedding_work(store_type) -> None:
    calls=[]
    def embed(text:str)->list[float]:
        calls.append(text)
        return [1.0,0.0]
    store=store_type(embedder=embed)
    store.add(CanonicalChunk(text="alpha",chunk_id="a"))
    before=list(calls)
    assert store.query("unused",top_k=0)==[]
    assert store.query_many(["unused-a","unused-b"],top_k=0)==[[],[]]
    assert calls==before


@pytest.mark.parametrize("store_type",[CanonicalVectorStore,AIVectorStore])
def test_diverse_query_spends_context_budget_on_complementary_evidence(store_type) -> None:
    vectors={
        "query":[1.0,0.0,0.0],
        "alpha":[0.9,0.435889894,0.0],
        "alpha-copy":[0.9,0.435889894,0.0],
        "beta":[0.85,0.0,0.526782688],
    }
    store=store_type(embedder=lambda text:list(vectors[text]))
    for name in ("alpha","alpha-copy","beta"):
        store.add(CanonicalChunk(text=name,chunk_id=name))
    assert [row.chunk.chunk_id for row in store.query("query",top_k=2)]==[
        "alpha","alpha-copy"
    ]
    diverse=store.query_diverse(
        "query",top_k=2,candidate_multiplier=3,diversity=0.5
    )
    assert [row.chunk.chunk_id for row in diverse]==["alpha","beta"]


@pytest.mark.parametrize("store_type",[CanonicalVectorStore,AIVectorStore])
def test_diverse_query_validates_bounded_controls(store_type) -> None:
    store=store_type(dims=8)
    store.add(CanonicalChunk(text="alpha beta",chunk_id="a"))
    with pytest.raises(ValueError,match="candidate_multiplier"):
        store.query_diverse("alpha",candidate_multiplier=0)
    with pytest.raises(ValueError,match="diversity"):
        store.query_diverse("alpha",diversity=1.1)

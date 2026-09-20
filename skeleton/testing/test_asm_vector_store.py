from __future__ import annotations

import math

import pytest

from skeleton.memory.asm_vector_accelerator import (
    AsmVectorHit,
    AsmVectorSearchAccelerator,
)
from skeleton.memory.core import Chunk
from skeleton.memory.vector import VectorStore


class _FakeKernel:
    def __init__(self) -> None:
        self.calls = 0
        self.matrix_ids: list[int] = []

    def dot_matrix_f32(
        self,
        query: list[float],
        matrix: object,
        *,
        rows: int,
        dimensions: int,
    ) -> list[float]:
        self.calls += 1
        self.matrix_ids.append(id(matrix))
        values = list(matrix)
        return [
            sum(
                query[column] * values[row * dimensions + column]
                for column in range(dimensions)
            )
            for row in range(rows)
        ]


class _FakeAsmSearch:
    minimum_candidates = 1

    def __init__(self, *, fail: bool = False) -> None:
        self.calls = 0
        self.batch_calls = 0
        self.fail = fail

    @staticmethod
    def _score(
        query: list[float],
        query_norm: float,
        candidates: list[tuple[list[float], float]],
    ) -> list[AsmVectorHit]:
        hits = [
            AsmVectorHit(
                index=index,
                similarity=sum(q * value for q, value in zip(query, vector))
                / (query_norm * norm),
            )
            for index, (vector, norm) in enumerate(candidates)
        ]
        hits.sort(key=lambda hit: (-hit.similarity, hit.index))
        return hits

    def top_k(
        self,
        query: list[float],
        query_norm: float,
        candidates: list[tuple[list[float], float]],
        top_k: int,
    ) -> list[AsmVectorHit]:
        self.calls += 1
        if self.fail:
            raise RuntimeError("simulated Assembly failure")
        return self._score(query, query_norm, candidates)[:top_k]

    def top_k_many(
        self,
        queries: list[tuple[list[float], float]],
        candidates: list[tuple[list[float], float]],
        top_k: int,
    ) -> list[list[AsmVectorHit]]:
        self.batch_calls += 1
        if self.fail:
            raise RuntimeError("simulated Assembly batch failure")
        return [
            self._score(query, query_norm, candidates)[:top_k]
            for query, query_norm in queries
        ]

    def range_search(
        self,
        query: list[float],
        query_norm: float,
        candidates: list[tuple[list[float], float]],
        similarity_threshold: float,
        *,
        max_hits: int,
    ) -> list[AsmVectorHit]:
        self.calls += 1
        if self.fail:
            raise RuntimeError("simulated Assembly range failure")
        hits = [
            hit
            for hit in self._score(query, query_norm, candidates)
            if hit.similarity >= similarity_threshold
        ]
        if len(hits) > max_hits:
            raise ValueError("range result bound exceeded")
        return hits

    def range_search_many(
        self,
        queries: list[tuple[list[float], float]],
        candidates: list[tuple[list[float], float]],
        similarity_threshold: float,
        *,
        max_total_hits: int,
    ) -> list[list[AsmVectorHit]]:
        self.batch_calls += 1
        if self.fail:
            raise RuntimeError("simulated Assembly batch range failure")
        batches = [
            [
                hit
                for hit in self._score(query, query_norm, candidates)
                if hit.similarity >= similarity_threshold
            ]
            for query, query_norm in queries
        ]
        if sum(len(batch) for batch in batches) > max_total_hits:
            raise ValueError("batch range result bound exceeded")
        return batches


class _FailJvm:
    minimum_candidates = 1

    def top_k(self, *args: object, **kwargs: object) -> list[object]:
        raise RuntimeError("simulated JVM failure")


class _SuccessfulJvm:
    minimum_candidates = 1

    def __init__(self) -> None:
        self.calls = 0

    def top_k(
        self,
        query: list[float],
        query_norm: float,
        candidates: list[tuple[list[float], float]],
        top_k: int,
    ) -> list[AsmVectorHit]:
        self.calls += 1
        return _FakeAsmSearch._score(query, query_norm, candidates)[:top_k]


_VECTORS = {
    "probe": [1.0, 0.0, 0.0],
    "query": [1.0, 0.0, 0.0],
    "alpha": [1.0, 0.0, 0.0],
    "alpha-tie": [1.0, 0.0, 0.0],
    "diagonal": [0.5, 0.5, 0.0],
    "orthogonal": [0.0, 1.0, 0.0],
    "opposite": [-1.0, 0.0, 0.0],
}


def _embed(text: str) -> list[float]:
    return list(_VECTORS[text])


def _build_store(
    *,
    use_asm: bool,
    asm_accelerator: object | None = None,
    use_jvm: bool = False,
    jvm_accelerator: object | None = None,
) -> VectorStore:
    store = VectorStore(
        embedder=_embed,
        use_jvm_acceleration=use_jvm,
        accelerator=jvm_accelerator,
        use_asm_acceleration=use_asm,
        asm_accelerator=asm_accelerator,
    )
    for name in ("alpha", "alpha-tie", "diagonal", "orthogonal", "opposite"):
        store.add(
            Chunk(
                text=name,
                chunk_id=name,
                metadata={"group": "keep" if name != "opposite" else "drop"},
            )
        )
    return store


def test_asm_search_adapter_top_k_preserves_stable_ties() -> None:
    kernel = _FakeKernel()
    accelerator = AsmVectorSearchAccelerator(kernel=kernel, minimum_candidates=1)
    candidates = [
        ([1.0, 0.0, 0.0], 1.0),
        ([1.0, 0.0, 0.0], 1.0),
        ([0.5, 0.5, 0.0], math.sqrt(0.5)),
        ([0.0, 1.0, 0.0], 1.0),
    ]

    hits = accelerator.top_k([1.0, 0.0, 0.0], 1.0, candidates, 4)

    assert [hit.index for hit in hits] == [0, 1, 2, 3]
    assert [hit.similarity for hit in hits] == pytest.approx(
        [1.0, 1.0, math.sqrt(0.5), 0.0]
    )
    assert kernel.calls == 1


def test_asm_search_adapter_batch_reuses_candidate_matrix() -> None:
    kernel = _FakeKernel()
    accelerator = AsmVectorSearchAccelerator(kernel=kernel, minimum_candidates=1)
    candidates = [
        ([1.0, 0.0], 1.0),
        ([0.0, 1.0], 1.0),
        ([0.5, 0.5], math.sqrt(0.5)),
    ]

    batches = accelerator.top_k_many(
        [([1.0, 0.0], 1.0), ([0.0, 1.0], 1.0)],
        candidates,
        3,
    )

    assert [[hit.index for hit in batch] for batch in batches] == [
        [0, 2, 1],
        [1, 2, 0],
    ]
    assert kernel.calls == 2
    assert len(set(kernel.matrix_ids)) == 1


def test_asm_search_adapter_range_enforces_total_bound() -> None:
    accelerator = AsmVectorSearchAccelerator(
        kernel=_FakeKernel(),
        minimum_candidates=1,
    )
    candidates = [
        ([1.0, 0.0], 1.0),
        ([0.9, 0.1], math.sqrt(0.82)),
        ([0.8, 0.2], math.sqrt(0.68)),
    ]

    with pytest.raises(ValueError, match="batch range result bound exceeded"):
        accelerator.range_search_many(
            [([1.0, 0.0], 1.0), ([1.0, 0.0], 1.0)],
            candidates,
            -1.0,
            max_total_hits=5,
        )


def test_vector_store_asm_fast_path_matches_python() -> None:
    baseline = _build_store(use_asm=False)
    fake = _FakeAsmSearch()
    accelerated = _build_store(use_asm=True, asm_accelerator=fake)

    expected = baseline.query("query", top_k=4)
    actual = accelerated.query("query", top_k=4)

    assert [row.chunk.chunk_id for row in actual] == [
        row.chunk.chunk_id for row in expected
    ]
    assert [row.score for row in actual] == pytest.approx(
        [row.score for row in expected]
    )
    stats = accelerated.acceleration_stats()
    assert stats["asm_enabled"] is True
    assert stats["asm_attempts"] == 1
    assert stats["asm_successes"] == 1
    assert fake.calls == 1


def test_vector_store_asm_batch_and_range_paths_match_python() -> None:
    baseline = _build_store(use_asm=False)
    fake = _FakeAsmSearch()
    accelerated = _build_store(use_asm=True, asm_accelerator=fake)
    queries = ["query", "orthogonal", "diagonal"]

    expected_top_k = [baseline.query(text, top_k=3) for text in queries]
    actual_top_k = accelerated.query_many(queries, top_k=3)
    expected_range = [
        baseline.query_threshold(text, minimum_score=0.6)
        for text in queries
    ]
    actual_range = accelerated.query_threshold_many(
        queries,
        minimum_score=0.6,
    )

    assert [
        [row.chunk.chunk_id for row in batch]
        for batch in actual_top_k
    ] == [
        [row.chunk.chunk_id for row in batch]
        for batch in expected_top_k
    ]
    assert [
        [row.chunk.chunk_id for row in batch]
        for batch in actual_range
    ] == [
        [row.chunk.chunk_id for row in batch]
        for batch in expected_range
    ]
    stats = accelerated.acceleration_stats()
    assert stats["asm_batch_successes"] == 1
    assert stats["asm_range_successes"] == 1


def test_vector_store_jvm_failure_falls_through_to_asm() -> None:
    baseline = _build_store(use_asm=False)
    asm = _FakeAsmSearch()
    accelerated = _build_store(
        use_asm=True,
        asm_accelerator=asm,
        use_jvm=True,
        jvm_accelerator=_FailJvm(),
    )

    expected = baseline.query("query", top_k=3)
    actual = accelerated.query("query", top_k=3)

    assert [row.chunk.chunk_id for row in actual] == [
        row.chunk.chunk_id for row in expected
    ]
    stats = accelerated.acceleration_stats()
    assert stats["fallbacks"] == 1
    assert stats["asm_successes"] == 1
    assert asm.calls == 1


def test_vector_store_successful_jvm_keeps_existing_precedence() -> None:
    jvm = _SuccessfulJvm()
    asm = _FakeAsmSearch()
    store = _build_store(
        use_asm=True,
        asm_accelerator=asm,
        use_jvm=True,
        jvm_accelerator=jvm,
    )

    results = store.query("query", top_k=3)

    assert len(results) == 3
    assert jvm.calls == 1
    assert asm.calls == 0
    stats = store.acceleration_stats()
    assert stats["successes"] == 1
    assert stats["asm_attempts"] == 0


def test_vector_store_asm_failure_falls_back_to_python() -> None:
    baseline = _build_store(use_asm=False)
    accelerated = _build_store(
        use_asm=True,
        asm_accelerator=_FakeAsmSearch(fail=True),
    )

    expected = baseline.query("query", top_k=5)
    actual = accelerated.query("query", top_k=5)

    assert [row.chunk.chunk_id for row in actual] == [
        row.chunk.chunk_id for row in expected
    ]
    assert [row.score for row in actual] == pytest.approx(
        [row.score for row in expected]
    )
    assert accelerated.acceleration_stats()["asm_fallbacks"] == 1

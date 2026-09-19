from __future__ import annotations

import math
import shutil
import subprocess
from pathlib import Path

import pytest

from skeleton.memory.core import Chunk
from skeleton.memory.jvm_vector_accelerator import (
    JvmVectorAccelerator,
    JvmVectorConfig,
    VectorHit,
)
from skeleton.memory.vector import VectorStore


class _FakeVectorAccelerator:
    minimum_candidates = 1

    def __init__(self) -> None:
        self.calls = 0
        self.batch_calls = 0

    def top_k(
        self,
        query: list[float],
        query_norm: float,
        candidates: list[tuple[list[float], float]],
        top_k: int,
    ) -> list[VectorHit]:
        self.calls += 1
        scored: list[VectorHit] = []
        for index, (vector, norm) in enumerate(candidates):
            dot = sum(q * value for q, value in zip(query, vector))
            scored.append(VectorHit(index=index, similarity=dot / (query_norm * norm)))
        scored.sort(key=lambda hit: (-hit.similarity, hit.index))
        return scored[:top_k]



    def top_k_many(
        self,
        queries: list[tuple[list[float], float]],
        candidates: list[tuple[list[float], float]],
        top_k: int,
    ) -> list[list[VectorHit]]:
        self.batch_calls += 1
        batches: list[list[VectorHit]] = []
        for query, query_norm in queries:
            scored: list[VectorHit] = []
            for index, (vector, norm) in enumerate(candidates):
                dot = sum(q * value for q, value in zip(query, vector))
                scored.append(
                    VectorHit(index=index, similarity=dot / (query_norm * norm))
                )
            scored.sort(key=lambda hit: (-hit.similarity, hit.index))
            batches.append(scored[:top_k])
        return batches


    def range_search(
        self,
        query: list[float],
        query_norm: float,
        candidates: list[tuple[list[float], float]],
        similarity_threshold: float,
        *,
        max_hits: int,
    ) -> list[VectorHit]:
        self.calls += 1
        scored: list[VectorHit] = []
        for index, (vector, norm) in enumerate(candidates):
            dot = sum(q * value for q, value in zip(query, vector))
            similarity = dot / (query_norm * norm)
            if similarity >= similarity_threshold:
                scored.append(VectorHit(index=index, similarity=similarity))
        scored.sort(key=lambda hit: (-hit.similarity, hit.index))
        if len(scored) > max_hits:
            raise RuntimeError("range result bound exceeded")
        return scored

    def range_search_many(
        self,
        queries: list[tuple[list[float], float]],
        candidates: list[tuple[list[float], float]],
        similarity_threshold: float,
        *,
        max_total_hits: int,
    ) -> list[list[VectorHit]]:
        self.batch_calls += 1
        batches: list[list[VectorHit]] = []
        total = 0
        for query, query_norm in queries:
            scored: list[VectorHit] = []
            for index, (vector, norm) in enumerate(candidates):
                dot = sum(q * value for q, value in zip(query, vector))
                similarity = dot / (query_norm * norm)
                if similarity >= similarity_threshold:
                    scored.append(VectorHit(index=index, similarity=similarity))
            scored.sort(key=lambda hit: (-hit.similarity, hit.index))
            total += len(scored)
            if total > max_total_hits:
                raise RuntimeError("batch range result bound exceeded")
            batches.append(scored)
        return batches
class _FailingVectorAccelerator:
    minimum_candidates = 1

    def top_k(self, *args: object, **kwargs: object) -> list[VectorHit]:
        raise RuntimeError("simulated vector JVM failure")

    def top_k_many(self, *args: object, **kwargs: object) -> list[list[VectorHit]]:
        raise RuntimeError("simulated vector JVM batch failure")

    def range_search(self, *args: object, **kwargs: object) -> list[VectorHit]:
        raise RuntimeError("simulated vector JVM range failure")

    def range_search_many(self, *args: object, **kwargs: object) -> list[list[VectorHit]]:
        raise RuntimeError("simulated vector JVM batch range failure")


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


def _build_store(*, accelerated: bool, accelerator: object | None = None) -> VectorStore:
    store = VectorStore(
        embedder=_embed,
        use_jvm_acceleration=accelerated,
        accelerator=accelerator,
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


def _signature(results: list[object]) -> list[tuple[str, float]]:
    return [
        (result.chunk.chunk_id, result.score)
        for result in results
    ]


def test_vector_store_jvm_fast_path_matches_python_and_keeps_stable_ties() -> None:
    baseline = _build_store(accelerated=False)
    fake = _FakeVectorAccelerator()
    accelerated = _build_store(accelerated=True, accelerator=fake)

    expected = baseline.query("query", top_k=4)
    actual = accelerated.query("query", top_k=4)

    assert [chunk for chunk, _ in _signature(actual)] == [
        chunk for chunk, _ in _signature(expected)
    ]
    assert [score for _, score in _signature(actual)] == pytest.approx(
        [score for _, score in _signature(expected)]
    )
    assert [row.chunk.chunk_id for row in actual[:2]] == ["alpha", "alpha-tie"]
    assert fake.calls == 1
    assert accelerated.acceleration_stats()["successes"] == 1


def test_vector_store_filters_metadata_before_java_scoring() -> None:
    fake = _FakeVectorAccelerator()
    store = _build_store(accelerated=True, accelerator=fake)

    results = store.query("query", top_k=10, metadata_filter={"group": "keep"})

    assert all(result.chunk.metadata["group"] == "keep" for result in results)
    assert "opposite" not in [result.chunk.chunk_id for result in results]
    assert fake.calls == 1


def test_vector_store_jvm_failure_falls_back_without_changing_results() -> None:
    baseline = _build_store(accelerated=False)
    accelerated = _build_store(
        accelerated=True,
        accelerator=_FailingVectorAccelerator(),
    )

    expected = baseline.query("query", top_k=5)
    actual = accelerated.query("query", top_k=5)

    assert [row.chunk.chunk_id for row in actual] == [
        row.chunk.chunk_id for row in expected
    ]
    assert [row.score for row in actual] == pytest.approx(
        [row.score for row in expected]
    )
    assert accelerated.acceleration_stats()["fallbacks"] == 1


def test_vector_store_small_candidate_sets_can_bypass_jvm() -> None:
    fake = _FakeVectorAccelerator()
    fake.minimum_candidates = 100
    store = _build_store(accelerated=True, accelerator=fake)

    results = store.query("query", top_k=3)

    assert len(results) == 3
    assert fake.calls == 0
    assert store.acceleration_stats()["bypassed_small_batch"] == 1


def test_vector_store_keeps_legacy_nonpositive_top_k_behavior_in_python() -> None:
    fake = _FakeVectorAccelerator()
    store = _build_store(accelerated=True, accelerator=fake)

    assert store.query("query", top_k=0) == []
    assert fake.calls == 0



def test_vector_store_batch_query_matches_repeated_python_queries() -> None:
    baseline = _build_store(accelerated=False)
    fake = _FakeVectorAccelerator()
    accelerated = _build_store(accelerated=True, accelerator=fake)
    texts = ["query", "orthogonal", "diagonal"]

    expected = [baseline.query(text, top_k=4) for text in texts]
    actual = accelerated.query_many(texts, top_k=4)

    assert [
        [row.chunk.chunk_id for row in batch]
        for batch in actual
    ] == [
        [row.chunk.chunk_id for row in batch]
        for batch in expected
    ]
    for actual_batch, expected_batch in zip(actual, expected):
        assert [row.score for row in actual_batch] == pytest.approx(
            [row.score for row in expected_batch]
        )
    assert fake.batch_calls == 1
    stats = accelerated.acceleration_stats()
    assert stats["batch_attempts"] == 1
    assert stats["batch_successes"] == 1
    assert accelerated.stats()["queries"] == len(texts)


def test_vector_store_batch_filters_candidates_once_before_jvm() -> None:
    fake = _FakeVectorAccelerator()
    store = _build_store(accelerated=True, accelerator=fake)

    actual = store.query_many(
        ["query", "orthogonal"],
        top_k=10,
        metadata_filter={"group": "keep"},
    )

    assert fake.batch_calls == 1
    for batch in actual:
        assert all(row.chunk.metadata["group"] == "keep" for row in batch)
        assert "opposite" not in [row.chunk.chunk_id for row in batch]


def test_vector_store_batch_failure_falls_back_for_every_query() -> None:
    baseline = _build_store(accelerated=False)
    accelerated = _build_store(
        accelerated=True,
        accelerator=_FailingVectorAccelerator(),
    )
    texts = ["query", "orthogonal", "diagonal"]

    expected = [baseline.query(text, top_k=3) for text in texts]
    actual = accelerated.query_many(texts, top_k=3)

    assert [
        [row.chunk.chunk_id for row in batch]
        for batch in actual
    ] == [
        [row.chunk.chunk_id for row in batch]
        for batch in expected
    ]
    for actual_batch, expected_batch in zip(actual, expected):
        assert [row.score for row in actual_batch] == pytest.approx(
            [row.score for row in expected_batch]
        )
    assert accelerated.acceleration_stats()["fallbacks"] == 1


def test_vector_store_threshold_query_matches_python_and_preserves_ties() -> None:
    baseline = _build_store(accelerated=False)
    fake = _FakeVectorAccelerator()
    accelerated = _build_store(accelerated=True, accelerator=fake)

    expected = baseline.query_threshold("query", minimum_score=0.75)
    actual = accelerated.query_threshold("query", minimum_score=0.75)

    assert [row.chunk.chunk_id for row in actual] == [
        row.chunk.chunk_id for row in expected
    ]
    assert [row.score for row in actual] == pytest.approx(
        [row.score for row in expected]
    )
    assert [row.chunk.chunk_id for row in actual] == [
        "alpha",
        "alpha-tie",
        "diagonal",
    ]
    assert accelerated.acceleration_stats()["range_successes"] == 1


def test_vector_store_threshold_filters_metadata_before_java() -> None:
    fake = _FakeVectorAccelerator()
    store = _build_store(accelerated=True, accelerator=fake)

    results = store.query_threshold(
        "query",
        minimum_score=0.0,
        metadata_filter={"group": "keep"},
    )

    assert all(row.chunk.metadata["group"] == "keep" for row in results)
    assert "opposite" not in [row.chunk.chunk_id for row in results]


def test_vector_store_threshold_failure_falls_back() -> None:
    baseline = _build_store(accelerated=False)
    accelerated = _build_store(
        accelerated=True,
        accelerator=_FailingVectorAccelerator(),
    )

    expected = baseline.query_threshold("query", minimum_score=0.5)
    actual = accelerated.query_threshold("query", minimum_score=0.5)

    assert [row.chunk.chunk_id for row in actual] == [
        row.chunk.chunk_id for row in expected
    ]
    assert accelerated.acceleration_stats()["fallbacks"] == 1


def test_vector_store_threshold_result_cap_survives_jvm_fallback() -> None:
    store = _build_store(
        accelerated=True,
        accelerator=_FailingVectorAccelerator(),
    )

    with pytest.raises(ValueError, match="threshold result bound"):
        store.query_threshold(
            "query",
            minimum_score=0.0,
            max_results=2,
        )


def test_vector_store_threshold_many_matches_repeated_queries() -> None:
    baseline = _build_store(accelerated=False)
    fake = _FakeVectorAccelerator()
    accelerated = _build_store(accelerated=True, accelerator=fake)
    texts = ["query", "orthogonal", "diagonal"]

    expected = [
        baseline.query_threshold(text, minimum_score=0.6)
        for text in texts
    ]
    actual = accelerated.query_threshold_many(
        texts,
        minimum_score=0.6,
    )

    assert [
        [row.chunk.chunk_id for row in batch]
        for batch in actual
    ] == [
        [row.chunk.chunk_id for row in batch]
        for batch in expected
    ]
    assert accelerated.acceleration_stats()["range_successes"] == 1
    assert accelerated.stats()["queries"] == len(texts)


def test_vector_store_threshold_validates_public_score_contract() -> None:
    store = _build_store(accelerated=False)
    for invalid in (-0.01, 1.01, math.inf, math.nan, True):
        with pytest.raises(ValueError, match="minimum_score"):
            store.query_threshold("query", invalid)

def _java_major(java: str) -> int | None:
    completed = subprocess.run(
        [java, "-version"],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    lines = (completed.stderr or completed.stdout).splitlines()
    if not lines:
        return None
    line = lines[0]
    marker = 'version "'
    if marker not in line:
        return None
    version = line.split(marker, 1)[1].split('"', 1)[0]
    head = version.split(".", 1)[0]
    if head == "1" and "." in version:
        head = version.split(".", 2)[1]
    try:
        return int(head)
    except ValueError:
        return None


def _real_config() -> JvmVectorConfig:
    java = shutil.which("java")
    if not java:
        pytest.skip("java is not installed")
    major = _java_major(java)
    if major is None or major < 21:
        pytest.skip("Java 21+ is required for the vector accelerator CI contract")
    source = (
        Path(__file__).resolve().parents[2]
        / "java-accelerators"
        / "vector"
        / "VectorSearchMain.java"
    )
    return JvmVectorConfig(
        java_binary=java,
        source=source,
        response_timeout_seconds=20,
        minimum_candidates=1,
    )


def test_real_java_vector_top_k_roundtrip_is_stable() -> None:
    query = [1.0, 0.0]
    candidates = [
        ([1.0, 0.0], 1.0),
        ([1.0, 0.0], 1.0),
        ([0.5, 0.5], math.sqrt(0.5)),
        ([0.0, 1.0], 1.0),
        ([-1.0, 0.0], 1.0),
    ]

    with JvmVectorAccelerator(_real_config()) as accelerator:
        assert accelerator.ping() >= 1
        hits = accelerator.top_k(query, 1.0, candidates, 4)

    assert [hit.index for hit in hits] == [0, 1, 2, 3]
    assert [hit.similarity for hit in hits] == pytest.approx(
        [1.0, 1.0, math.sqrt(0.5), 0.0]
    )



def test_real_java_batch_vector_roundtrip_reuses_candidate_matrix() -> None:
    queries = [
        ([1.0, 0.0], 1.0),
        ([0.0, 1.0], 1.0),
    ]
    candidates = [
        ([1.0, 0.0], 1.0),
        ([1.0, 0.0], 1.0),
        ([0.5, 0.5], math.sqrt(0.5)),
        ([0.0, 1.0], 1.0),
        ([-1.0, 0.0], 1.0),
    ]

    with JvmVectorAccelerator(_real_config()) as accelerator:
        batches = accelerator.top_k_many(queries, candidates, 3)

    assert [[hit.index for hit in batch] for batch in batches] == [
        [0, 1, 2],
        [3, 2, 0],
    ]
    assert [hit.similarity for hit in batches[0]] == pytest.approx(
        [1.0, 1.0, math.sqrt(0.5)]
    )
    assert [hit.similarity for hit in batches[1]] == pytest.approx(
        [1.0, math.sqrt(0.5), 0.0]
    )


def test_real_java_vector_store_batch_matches_python_store() -> None:
    baseline = _build_store(accelerated=False)
    accelerator = JvmVectorAccelerator(_real_config())
    accelerated = _build_store(accelerated=True, accelerator=accelerator)
    texts = ["query", "orthogonal", "diagonal"]

    try:
        expected = [baseline.query(text, top_k=4) for text in texts]
        actual = accelerated.query_many(texts, top_k=4)
    finally:
        accelerator.close()

    assert [
        [row.chunk.chunk_id for row in batch]
        for batch in actual
    ] == [
        [row.chunk.chunk_id for row in batch]
        for batch in expected
    ]
    for actual_batch, expected_batch in zip(actual, expected):
        assert [row.score for row in actual_batch] == pytest.approx(
            [row.score for row in expected_batch]
        )


def test_real_java_vector_range_search_roundtrip_is_stable() -> None:
    query = [1.0, 0.0]
    candidates = [
        ([1.0, 0.0], 1.0),
        ([1.0, 0.0], 1.0),
        ([0.5, 0.5], math.sqrt(0.5)),
        ([0.0, 1.0], 1.0),
        ([-1.0, 0.0], 1.0),
    ]

    with JvmVectorAccelerator(_real_config()) as accelerator:
        hits = accelerator.range_search(
            query,
            1.0,
            candidates,
            0.70,
            max_hits=5,
        )

    assert [hit.index for hit in hits] == [0, 1, 2]
    assert [hit.similarity for hit in hits] == pytest.approx(
        [1.0, 1.0, math.sqrt(0.5)]
    )


def test_real_java_batch_range_search_reuses_candidate_matrix() -> None:
    queries = [
        ([1.0, 0.0], 1.0),
        ([0.0, 1.0], 1.0),
    ]
    candidates = [
        ([1.0, 0.0], 1.0),
        ([0.0, 1.0], 1.0),
        ([0.5, 0.5], math.sqrt(0.5)),
        ([-1.0, 0.0], 1.0),
    ]

    with JvmVectorAccelerator(_real_config()) as accelerator:
        batches = accelerator.range_search_many(
            queries,
            candidates,
            0.70,
            max_total_hits=10,
        )

    assert [[hit.index for hit in batch] for batch in batches] == [
        [0, 2],
        [1, 2],
    ]


def test_real_java_vector_store_threshold_matches_python_store() -> None:
    baseline = _build_store(accelerated=False)
    accelerator = JvmVectorAccelerator(_real_config())
    accelerated = _build_store(accelerated=True, accelerator=accelerator)

    try:
        expected = baseline.query_threshold("query", minimum_score=0.75)
        actual = accelerated.query_threshold("query", minimum_score=0.75)
    finally:
        accelerator.close()

    assert [row.chunk.chunk_id for row in actual] == [
        row.chunk.chunk_id for row in expected
    ]
    assert [row.score for row in actual] == pytest.approx(
        [row.score for row in expected]
    )

def test_real_java_vector_bridge_rejects_dimension_mismatch_before_ipc() -> None:
    with JvmVectorAccelerator(_real_config()) as accelerator:
        with pytest.raises(ValueError, match="dimension"):
            accelerator.top_k(
                [1.0, 0.0],
                1.0,
                [([1.0, 0.0, 0.0], 1.0)],
                1,
            )

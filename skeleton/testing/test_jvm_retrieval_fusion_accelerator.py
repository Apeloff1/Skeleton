from __future__ import annotations

import math
import shutil
import subprocess
from pathlib import Path

import pytest

from skeleton.retrieval.fusion import Fuser, FusionStrategy, ScoredResult
from skeleton.retrieval.jvm_fusion_accelerator import (
    FusionHit,
    JvmFusionAccelerator,
    JvmFusionConfig,
    JvmFusionProtocolError,
)


class _FakeFusionAccelerator:
    minimum_contributions = 1

    def __init__(self) -> None:
        self.calls = 0

    def aggregate_top_k(
        self,
        fragment_count: int,
        contributions: list[tuple[int, float]],
        top_k: int,
    ) -> list[FusionHit]:
        self.calls += 1
        scores = [0.0] * fragment_count
        seen = [False] * fragment_count
        for index, value in contributions:
            scores[index] += value
            seen[index] = True
        if not all(seen):
            raise RuntimeError("fragment without contribution")
        hits = [
            FusionHit(index=index, score=score)
            for index, score in enumerate(scores)
        ]
        hits.sort(key=lambda hit: (-hit.score, hit.index))
        return hits[:top_k]


class _FailingFusionAccelerator:
    minimum_contributions = 1

    def aggregate_top_k(
        self,
        *_args: object,
        **_kwargs: object,
    ) -> list[FusionHit]:
        raise RuntimeError("simulated JVM fusion failure")


def _result(
    fragment_id: str,
    score: float,
    *,
    plane: str,
    content: str | None = None,
) -> ScoredResult:
    return ScoredResult(
        fragment_id=fragment_id,
        content=content or fragment_id,
        score=score,
        plane=plane,
        provenance=f"source:{fragment_id}",
        metadata={"fragment": fragment_id},
    )


def _signature(results: list[ScoredResult]) -> list[tuple[str, float]]:
    return [(row.fragment_id, row.score) for row in results]


def _fixture() -> dict[str, list[ScoredResult]]:
    return {
        "rag": [
            _result("shared", 0.90, plane="rag"),
            _result("rag-only", 0.70, plane="rag"),
            _result("tie-a", 0.50, plane="rag"),
        ],
        "kag": [
            _result("shared", 0.80, plane="kag"),
            _result("kag-only", 0.70, plane="kag"),
            _result("tie-b", 0.50, plane="kag"),
        ],
        "mag": [
            _result("mag-only", 0.60, plane="mag"),
            _result("shared", 0.50, plane="mag"),
        ],
    }


@pytest.mark.parametrize(
    "strategy",
    [FusionStrategy.RRF, FusionStrategy.WEIGHTED],
)
def test_jvm_fusion_matches_python_order_and_objects(strategy: FusionStrategy) -> None:
    fixture = _fixture()
    baseline = Fuser(strategy=strategy)
    fake = _FakeFusionAccelerator()
    accelerated = Fuser(
        strategy=strategy,
        use_jvm_acceleration=True,
        accelerator=fake,
    )

    expected = baseline.fuse(fixture, top_k=5)
    actual = accelerated.fuse(fixture, top_k=5)

    assert [row.fragment_id for row in actual] == [
        row.fragment_id for row in expected
    ]
    assert all(
        actual[index] is expected[index]
        for index in range(len(actual))
    )
    assert fake.calls == 1
    stats = accelerated.acceleration_stats()
    assert stats["attempts"] == 1
    assert stats["successes"] == 1
    assert stats["fallbacks"] == 0


def test_jvm_rrf_preserves_first_seen_tie_order() -> None:
    first = _result("first", 1.0, plane="rag")
    second = _result("second", 1.0, plane="kag")
    fixture = {
        "rag": [first],
        "kag": [second],
    }
    accelerated = Fuser(
        strategy=FusionStrategy.RRF,
        use_jvm_acceleration=True,
        accelerator=_FakeFusionAccelerator(),
    )

    actual = accelerated.fuse(fixture, top_k=2)

    assert actual == [first, second]


def test_jvm_weighted_fusion_aggregates_duplicate_fragment_contributions() -> None:
    first_shared = _result("shared", 0.60, plane="rag")
    second_shared = _result("shared", 0.90, plane="kag")
    fixture = {
        "rag": [
            first_shared,
            _result("rag-only", 0.95, plane="rag"),
        ],
        "kag": [
            second_shared,
            _result("kag-only", 0.90, plane="kag"),
        ],
    }
    fake = _FakeFusionAccelerator()
    accelerated = Fuser(
        strategy=FusionStrategy.WEIGHTED,
        use_jvm_acceleration=True,
        accelerator=fake,
    )

    actual = accelerated.fuse(fixture, top_k=3)

    assert [row.fragment_id for row in actual] == [
        "shared",
        "rag-only",
        "kag-only",
    ]
    assert actual[0] is first_shared
    assert fake.calls == 1


def test_jvm_fusion_failure_falls_back_without_semantic_change() -> None:
    fixture = _fixture()
    expected = Fuser(strategy=FusionStrategy.RRF).fuse(
        fixture,
        top_k=6,
    )
    accelerated = Fuser(
        strategy=FusionStrategy.RRF,
        use_jvm_acceleration=True,
        accelerator=_FailingFusionAccelerator(),
    )

    actual = accelerated.fuse(fixture, top_k=6)

    assert [row.fragment_id for row in actual] == [
        row.fragment_id for row in expected
    ]
    stats = accelerated.acceleration_stats()
    assert stats["attempts"] == 1
    assert stats["successes"] == 0
    assert stats["fallbacks"] == 1


def test_jvm_fusion_small_batch_bypasses_accelerator() -> None:
    fake = _FakeFusionAccelerator()
    fake.minimum_contributions = 100
    accelerated = Fuser(
        strategy=FusionStrategy.RRF,
        use_jvm_acceleration=True,
        accelerator=fake,
    )

    actual = accelerated.fuse(
        {"rag": [_result("one", 1.0, plane="rag")]},
        top_k=1,
    )

    assert [row.fragment_id for row in actual] == ["one"]
    assert fake.calls == 0
    assert accelerated.acceleration_stats()["bypassed_small_batch"] == 1


def test_default_fuser_does_not_resolve_java() -> None:
    failing = _FailingFusionAccelerator()
    baseline = Fuser(
        strategy=FusionStrategy.RRF,
        accelerator=failing,
    )

    actual = baseline.fuse(
        {"rag": [_result("one", 1.0, plane="rag")]},
        top_k=1,
    )

    assert [row.fragment_id for row in actual] == ["one"]
    assert baseline.acceleration_stats()["attempts"] == 0


def test_nonpositive_top_k_keeps_legacy_python_behavior() -> None:
    fake = _FakeFusionAccelerator()
    accelerated = Fuser(
        strategy=FusionStrategy.RRF,
        use_jvm_acceleration=True,
        accelerator=fake,
    )
    fixture = {
        "rag": [
            _result("a", 1.0, plane="rag"),
            _result("b", 0.5, plane="rag"),
        ]
    }

    assert accelerated.fuse(fixture, top_k=0) == []
    assert fake.calls == 0


def test_first_strategy_never_invokes_jvm() -> None:
    fake = _FakeFusionAccelerator()
    accelerated = Fuser(
        strategy=FusionStrategy.FIRST,
        use_jvm_acceleration=True,
        accelerator=fake,
    )
    fixture = _fixture()

    actual = accelerated.fuse(fixture, top_k=2)

    assert [row.fragment_id for row in actual] == ["shared", "rag-only"]
    assert fake.calls == 0


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
    marker = 'version "'
    if marker not in lines[0]:
        return None
    version = lines[0].split(marker, 1)[1].split('"', 1)[0]
    head = version.split(".", 1)[0]
    if head == "1" and "." in version:
        head = version.split(".", 2)[1]
    try:
        return int(head)
    except ValueError:
        return None


def _real_config() -> JvmFusionConfig:
    java = shutil.which("java")
    if not java:
        pytest.skip("java is not installed")
    major = _java_major(java)
    if major is None or major < 21:
        pytest.skip("Java 21+ is required for retrieval fusion CI")
    source = (
        Path(__file__).resolve().parents[2]
        / "java-accelerators"
        / "retrieval"
        / "FusionMain.java"
    )
    return JvmFusionConfig(
        java_binary=java,
        source=source,
        response_timeout_seconds=20,
        minimum_contributions=1,
    )


def test_real_java_fusion_aggregate_roundtrip_is_stable() -> None:
    contributions = [
        (0, 1.0),
        (1, 0.5),
        (2, 0.75),
        (0, 0.25),
        (1, 0.75),
        (2, 0.5),
        (3, -0.25),
    ]

    with JvmFusionAccelerator(_real_config()) as accelerator:
        assert accelerator.ping() >= 1
        hits = accelerator.aggregate_top_k(
            4,
            contributions,
            3,
        )

    assert [hit.index for hit in hits] == [0, 1, 2]
    assert [hit.score for hit in hits] == pytest.approx(
        [1.25, 1.25, 1.25]
    )


@pytest.mark.parametrize(
    "strategy",
    [FusionStrategy.RRF, FusionStrategy.WEIGHTED],
)
def test_real_java_fuser_matches_python(strategy: FusionStrategy) -> None:
    fixture = _fixture()
    expected = Fuser(strategy=strategy).fuse(fixture, top_k=5)
    accelerator = JvmFusionAccelerator(_real_config())
    accelerated = Fuser(
        strategy=strategy,
        use_jvm_acceleration=True,
        accelerator=accelerator,
    )

    try:
        actual = accelerated.fuse(fixture, top_k=5)
    finally:
        accelerator.close()

    assert [row.fragment_id for row in actual] == [
        row.fragment_id for row in expected
    ]


def test_real_java_rejects_missing_fragment_contribution() -> None:
    with JvmFusionAccelerator(_real_config()) as accelerator:
        with pytest.raises(
            JvmFusionProtocolError,
            match="fragment without contribution",
        ):
            accelerator.aggregate_top_k(
                2,
                [(0, 1.0)],
                1,
            )


def test_bridge_rejects_invalid_contribution_before_ipc() -> None:
    accelerator = JvmFusionAccelerator(_real_config())
    try:
        with pytest.raises(ValueError, match="fragment index"):
            accelerator.aggregate_top_k(
                1,
                [(1, 1.0)],
                1,
            )
        with pytest.raises(ValueError, match="finite"):
            accelerator.aggregate_top_k(
                1,
                [(0, math.inf)],
                1,
            )
        assert accelerator.status().starts == 0
    finally:
        accelerator.close()

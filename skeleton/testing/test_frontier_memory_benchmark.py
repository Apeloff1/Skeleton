import pytest

from scripts.benchmark_frontier_memory import run_benchmark


@pytest.mark.asyncio
async def test_memory_benchmark_produces_comparable_evidence():
    report = await run_benchmark(items=12, queries=4, limit=3)

    assert report["workload"] == "frontier-memory-contract-v1"
    assert report["source_semantics"]["blob"] == (
        "b67167f1135744e74827ce03b0bf5d766e800cf4"
    )
    assert [result["backend"] for result in report["results"]] == [
        "in-memory-reference",
        "sqlite-collection",
    ]

    for result in report["results"]:
        assert result["items"] == 12
        assert result["queries"] == 4
        assert result["hits"] == 12
        assert result["write_seconds"] >= 0
        assert result["search_seconds"] >= 0
        assert result["write_ops_per_second"] is not None
        assert result["search_ops_per_second"] is not None

    assert report["results"][1]["persisted_items"] == 12

from __future__ import annotations

import pytest

from scripts.benchmark_frontier_encyclopedia import SOURCE_SEMANTICS, run_benchmark


def test_encyclopedia_benchmark_records_correctness_and_observational_timing():
    report = run_benchmark(iterations=12)

    assert report["workload"] == "frontier-encyclopedia-collection-v1"
    assert report["source_semantics"] == SOURCE_SEMANTICS
    assert report["configuration"] == {"iterations": 12}
    assert report["evidence"]["memory_projections"] == 12
    assert report["evidence"]["caught_total"] == 24
    assert report["evidence"]["stable_state_digests"] == 1
    assert report["evidence"]["replay_converges"] is True
    assert report["evidence"]["catalog_masking_holds"] is True
    assert report["evidence"]["invariants_hold"] is True
    assert report["timing"]["elapsed_seconds"] >= 0
    assert report["timing"]["latency_gate"] is False
    if report["timing"]["iterations_per_second"] is not None:
        assert report["timing"]["iterations_per_second"] > 0


@pytest.mark.parametrize("iterations", [0, -1])
def test_encyclopedia_benchmark_rejects_nonpositive_iterations(iterations):
    with pytest.raises(ValueError, match="positive"):
        run_benchmark(iterations=iterations)


def test_encyclopedia_benchmark_rejects_type_confusion():
    with pytest.raises(TypeError, match="integer"):
        run_benchmark(iterations=True)

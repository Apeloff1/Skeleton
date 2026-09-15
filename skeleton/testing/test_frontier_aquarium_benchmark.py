from __future__ import annotations

import pytest

from scripts.benchmark_frontier_aquarium import SOURCE_SEMANTICS, run_benchmark


def test_aquarium_benchmark_records_correctness_and_observational_timing():
    report = run_benchmark(iterations=12)

    assert report["workload"] == "frontier-aquarium-policy-v2"
    assert report["source_semantics"] == SOURCE_SEMANTICS
    assert report["configuration"] == {"iterations": 12}
    assert report["evidence"]["duplicate_rejected"] is True
    assert report["evidence"]["memory_projections"] == 12
    assert report["evidence"]["decorations_placed"] == 12
    assert report["evidence"]["unique_state_digests"] == 12
    assert report["evidence"]["invariants_hold"] is True
    assert report["timing"]["elapsed_seconds"] >= 0
    assert report["timing"]["latency_gate"] is False
    if report["timing"]["iterations_per_second"] is not None:
        assert report["timing"]["iterations_per_second"] > 0


@pytest.mark.parametrize("iterations", [0, -1])
def test_aquarium_benchmark_rejects_nonpositive_iterations(iterations):
    with pytest.raises(ValueError, match="positive"):
        run_benchmark(iterations=iterations)


def test_aquarium_benchmark_rejects_type_confusion():
    with pytest.raises(TypeError, match="integer"):
        run_benchmark(iterations=True)

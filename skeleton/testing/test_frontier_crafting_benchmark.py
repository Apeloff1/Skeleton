from __future__ import annotations

import pytest

from scripts.benchmark_frontier_crafting import SOURCE_SEMANTICS, run_benchmark


def test_crafting_benchmark_records_correctness_without_latency_gate():
    report = run_benchmark(iterations=32)
    assert report["workload"] == "frontier-crafting-policy-v1"
    assert report["source_semantics"] == SOURCE_SEMANTICS
    assert report["configuration"]["iterations"] == 32
    assert report["evidence"]["total_crafted"] == 32
    assert report["evidence"]["output_items"] == 64
    assert report["evidence"]["energy_restore_per_item"] == 25
    assert report["evidence"]["materials_exhausted_exactly"] is True
    assert report["evidence"]["invariants_hold"] is True
    assert report["timing"]["elapsed_seconds"] >= 0
    assert report["timing"]["latency_gate"] is False


def test_crafting_benchmark_rejects_empty_workload():
    with pytest.raises(ValueError, match="iterations must be positive"):
        run_benchmark(iterations=0)

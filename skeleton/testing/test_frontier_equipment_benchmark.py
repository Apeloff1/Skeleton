from __future__ import annotations

import pytest

from scripts.benchmark_frontier_equipment import SOURCE_SEMANTICS, run_benchmark


def test_equipment_benchmark_records_correctness_without_latency_gate():
    report = run_benchmark(iterations=32)
    assert report["workload"] == "frontier-equipment-policy-v1"
    assert report["source_semantics"] == SOURCE_SEMANTICS
    assert report["configuration"]["iterations"] == 32
    assert report["evidence"]["invariants_hold"] is True
    assert report["evidence"]["checksum"] > 0
    assert report["evidence"]["equipped"] == {
        "rod": "surf_rod",
        "line": "braid_line",
        "bobber": "glow_bobber",
    }
    assert report["timing"]["elapsed_seconds"] >= 0
    assert report["timing"]["latency_gate"] is False


def test_equipment_benchmark_rejects_empty_workload():
    with pytest.raises(ValueError, match="iterations must be positive"):
        run_benchmark(iterations=0)

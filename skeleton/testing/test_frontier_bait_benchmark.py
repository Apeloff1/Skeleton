from __future__ import annotations

import pytest

from scripts.benchmark_frontier_bait import SOURCE_SEMANTICS, run_benchmark


def test_bait_benchmark_records_correctness_without_latency_gate():
    report = run_benchmark(iterations=32)
    assert report["workload"] == "frontier-bait-policy-v1"
    assert report["source_semantics"] == SOURCE_SEMANTICS
    assert report["configuration"]["iterations"] == 32
    assert report["evidence"]["uses"] == 128
    assert report["evidence"]["checksum"] > 0
    assert report["evidence"]["invariants_hold"] is True
    assert report["timing"]["elapsed_seconds"] >= 0
    assert report["timing"]["latency_gate"] is False


def test_bait_benchmark_rejects_empty_workload():
    with pytest.raises(ValueError, match="iterations must be positive"):
        run_benchmark(iterations=0)

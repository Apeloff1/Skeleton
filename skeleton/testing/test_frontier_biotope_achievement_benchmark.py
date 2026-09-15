from __future__ import annotations

import pytest

from scripts.benchmark_frontier_biotope_achievements import (
    SOURCE_SEMANTICS,
    run_benchmark,
)


def test_biotope_achievement_benchmark_is_correctness_gated_only():
    report = run_benchmark(iterations=12)

    assert report["workload"] == "frontier-biotope-achievement-adapters-v1"
    assert report["source_semantics"] == SOURCE_SEMANTICS
    assert report["configuration"] == {"iterations": 12}
    assert report["evidence"]["qualified"] == 12
    assert report["evidence"]["lake_alias_updates"] == 12
    assert report["evidence"]["trophy_max_sum"] == 1440
    assert report["evidence"]["world_angler_each_rule_holds"] is True
    assert report["evidence"]["explicit_species_signals"] is True
    assert report["evidence"]["invariants_hold"] is True
    assert report["timing"]["elapsed_seconds"] >= 0
    assert report["timing"]["latency_gate"] is False
    if report["timing"]["iterations_per_second"] is not None:
        assert report["timing"]["iterations_per_second"] > 0


@pytest.mark.parametrize("iterations", [0, -1])
def test_biotope_achievement_benchmark_rejects_nonpositive_iterations(iterations):
    with pytest.raises(ValueError, match="positive"):
        run_benchmark(iterations=iterations)


def test_biotope_achievement_benchmark_rejects_type_confusion():
    with pytest.raises(TypeError, match="integer"):
        run_benchmark(iterations=True)

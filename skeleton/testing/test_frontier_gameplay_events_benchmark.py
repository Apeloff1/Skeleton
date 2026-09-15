from __future__ import annotations

import pytest

from scripts.benchmark_frontier_gameplay_events import SOURCE_SEMANTICS, run_benchmark


def test_gameplay_event_benchmark_is_correctness_gated_only():
    report = run_benchmark(iterations=12)

    assert report["workload"] == "frontier-gameplay-events-v1"
    assert report["source_semantics"] == SOURCE_SEMANTICS
    assert report["configuration"] == {"iterations": 12}
    assert report["evidence"]["memory_projections"] == 12
    assert report["evidence"]["challenge_awards"] == 12
    assert report["evidence"]["milestone_token_sum"] == 1200
    assert report["evidence"]["single_shot_challenge_rewards"] is True
    assert report["evidence"]["midnight_window_holds"] is True
    assert report["evidence"]["invariants_hold"] is True
    assert report["timing"]["elapsed_seconds"] >= 0
    assert report["timing"]["latency_gate"] is False
    if report["timing"]["iterations_per_second"] is not None:
        assert report["timing"]["iterations_per_second"] > 0


@pytest.mark.parametrize("iterations", [0, -1])
def test_gameplay_event_benchmark_rejects_nonpositive_iterations(iterations):
    with pytest.raises(ValueError, match="positive"):
        run_benchmark(iterations=iterations)


def test_gameplay_event_benchmark_rejects_type_confusion():
    with pytest.raises(TypeError, match="integer"):
        run_benchmark(iterations=True)

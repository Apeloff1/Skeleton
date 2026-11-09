from __future__ import annotations

import pytest

from scripts.benchmark_frontier_achievements import SOURCE_BLOB, run_benchmark


def test_achievement_benchmark_reports_semantics_without_latency_gate():
    result = run_benchmark(achievements=12, transitions=12)

    assert result["workload"] == "frontier-achievement-policy-v1"
    assert result["source_semantics"] == {
        "repository": "Apeloff1/Lorebuffa",
        "path": "backend/achievement_routes.py",
        "blob": SOURCE_BLOB,
        "equivalent_repository": "Apeloff1/Openworld",
    }
    assert result["configuration"] == {"achievements": 12, "transitions": 12}
    assert result["evidence"]["final_fish_caught"] == 12
    assert result["evidence"]["unlocked"] == 12
    assert result["evidence"]["projected_memory_items"] == 12
    assert result["evidence"]["unique_memory_ids"] == 12
    assert result["evidence"]["summary"] == {
        "total": 12,
        "unlocked": 12,
        "claimed": 0,
        "completion_percent": 100.0,
    }

    timing = result["timing"]
    assert timing["normalize_seconds"] >= 0
    assert timing["progress_seconds"] >= 0
    assert timing["unlock_seconds"] >= 0
    assert timing["projection_seconds"] >= 0
    assert timing["transition_ops_per_second"] is None or timing[
        "transition_ops_per_second"
    ] >= 0
    assert timing["projection_ops_per_second"] is None or timing[
        "projection_ops_per_second"
    ] >= 0


def test_achievement_benchmark_partial_unlock_count_is_deterministic():
    result = run_benchmark(achievements=20, transitions=7)
    assert result["evidence"]["final_fish_caught"] == 7
    assert result["evidence"]["unlocked"] == 7
    assert result["evidence"]["projected_memory_items"] == 7
    assert result["evidence"]["summary"]["completion_percent"] == 35.0


@pytest.mark.parametrize(
    ("achievements", "transitions"),
    [(0, 1), (1, 0), (-1, 1), (1, -1)],
)
def test_achievement_benchmark_rejects_invalid_configuration(
    achievements: int,
    transitions: int,
):
    with pytest.raises(ValueError, match="must be positive"):
        run_benchmark(achievements=achievements, transitions=transitions)

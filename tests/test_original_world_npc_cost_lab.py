"""Measured CPU work, not synthetic promises of faster simulation."""
from __future__ import annotations

import pytest

from skeleton.game.generation.original_foundation_compiler import FoundationError
from skeleton.game.generation.original_world_npc_cost_lab import (
    BENCH_SCHEMA, benchmark_era, main,
)


def test_actual_early_era_cognitive_budget_equals_real_physical_capacity():
    report = benchmark_era("paleolithic", "economy", turns=2)
    assert report["schema"] == BENCH_SCHEMA
    assert report["world_turns_actually_advanced"] == 2
    assert 1 <= report["scheduled_max_per_turn"] <= 3
    assert report["local_cognitive_action_slots_used"] <= 6
    assert report["actual_wall_time_ns"] > 0
    assert report["actual_mean_ns_per_world_turn"] > 0
    assert len(report["final_real_save_sha256"]) == 64


def test_measured_brain_slot_reduction_without_replacing_real_npc_bodies():
    small = benchmark_era("near-future", "economy", turns=2)
    deep = benchmark_era("near-future", "unrestricted", turns=2)
    assert small["local_physically_simulated_NPCs"] == deep[
        "local_physically_simulated_NPCs"]
    assert small["regional_census_before"] == deep["regional_census_before"]
    assert small["local_cognitive_action_slots_used"] == 6
    assert deep["local_cognitive_action_slots_used"] == (
        deep["local_physically_simulated_NPCs"] * 2)
    assert small["local_brain_slots_saved_against_full_simulation"] > 0
    assert deep["local_brain_slots_saved_against_full_simulation"] == 0
    # Actual timings can vary due to host contention; don't lie with
    # an artificially guaranteed speedup ratio.


def test_benchmark_reproducible_state_but_not_made_up_wall_time():
    one = benchmark_era("iron-age", "balanced", turns=2)
    two = benchmark_era("iron-age", "balanced", turns=2)
    assert one["final_real_save_sha256"] == two["final_real_save_sha256"]
    assert one["local_cognitive_action_slots_used"] == two[
        "local_cognitive_action_slots_used"]
    assert one["actual_wall_time_ns"] > 0
    assert two["actual_wall_time_ns"] > 0


def test_invalid_runtime_workloads_rejected_before_measurement():
    for kwargs in (
        {"era": "invented-hardware"},
        {"era": "iron-age", "preset": "free-infinite"},
        {"era": "iron-age", "turns": 1000},
    ):
        with pytest.raises(FoundationError):
            benchmark_era(**kwargs)


def test_cli_prints_measured_results(capsys):
    assert main(["--era", "iron-age", "--preset", "economy",
                 "--turns", "1"]) == 0
    text = capsys.readouterr().out
    assert '"actual_wall_time_ns":' in text
    assert '"local_brain_slots_saved_against_full_simulation":' in text

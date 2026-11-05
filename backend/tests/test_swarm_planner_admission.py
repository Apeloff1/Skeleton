"""Swarm planner: explicit empty inputs, bounded budgets and source-unique receipt IDs."""
from __future__ import annotations

import pytest

from core import swarm_planner as planner


def test_none_uses_default_phases_but_empty_list_fails_closed():
    assert planner.plan_build("b", phases=None)["phase_count"] == len(planner.DEFAULT_PHASES)
    with pytest.raises(ValueError, match="at least one phase"):
        planner.plan_build("b", phases=[])


def test_explicit_empty_dependency_map_means_parallel_not_sequential():
    result = planner.plan_build("b", phases=["a", "b", "c"], deps={}, seed=3)
    assert result["waves"] == [{"wave": 0, "phases": ["a", "b", "c"]}]
    assert result["critical_path_len"] == 1
    assert planner.verify_plan(result)["valid"] is True


def test_none_dependencies_preserve_sequential_default():
    result = planner.plan_build("b", phases=["a", "b", "c"], deps=None, seed=3)
    assert [wave["phases"] for wave in result["waves"]] == [["a"], ["b"], ["c"]]


@pytest.mark.parametrize("phases", [
    [],
    [""],
    ["\n"],
    [42],
    ["x"] * 501,
    ["a", "a"],
    "ab",
])
def test_malformed_phases_do_not_expand_into_100_default_phases(phases):
    with pytest.raises(ValueError):
        planner.plan_build("b", phases=phases)


@pytest.mark.parametrize("platoon_size", [0, -5, float("nan"), float("inf"), 2.5, True])
def test_invalid_platoon_budgets_fail_before_worker_assignment(platoon_size):
    with pytest.raises(ValueError, match="platoon_size"):
        planner.plan_build("b", phases=["a"], platoon_size=platoon_size)


def test_large_integral_platoon_remains_safely_clamped():
    result = planner.plan_build("b", phases=["a"], platoon_size=999)
    assert result["platoon_size"] == planner.MAX_PLATOON


@pytest.mark.parametrize("deps", [
    {"not-a-phase": ["a"]},
    {"a": ["missing"]},
    {"a": ["b", "b"]},
    {"a": "b"},
])
def test_invalid_dependency_graph_fails_closed(deps):
    with pytest.raises(ValueError):
        planner.plan_build("b", phases=["a", "b"], deps=deps)


@pytest.mark.parametrize("objectives", [[], [""], [None], ["x" * 513], "not-a-list"])
def test_empty_and_invalid_objectives_do_not_invent_goals(objectives):
    with pytest.raises(ValueError, match="objectives"):
        planner.plan_build("b", phases=["a"], objectives=objectives)


def test_plan_receipt_binds_build_identity_and_objectives():
    common = {"phases": ["a", "b"], "deps": {}, "seed": 7}
    a = planner.plan_build("build-A", objectives=["ship game"], **common)
    b = planner.plan_build("build-B", objectives=["ship game"], **common)
    c = planner.plan_build("build-A", objectives=["ship engine"], **common)
    same = planner.plan_build("build-A", objectives=["ship game"], **common)
    assert a["plan_hash"] != b["plan_hash"]
    assert a["plan_hash"] != c["plan_hash"]
    assert a["plan_hash"] == same["plan_hash"]
    assert planner.verify_plan(a)["valid"] is True


@pytest.mark.parametrize("build_id", ["", " ", 42, "a" * 129])
def test_build_identity_is_bounded(build_id):
    with pytest.raises(ValueError, match="build_id"):
        planner.plan_build(build_id, phases=["a"])


@pytest.mark.parametrize("context", [{"genre": "a" * 257}, {"genre": {"malformed": True}}])
def test_genre_source_is_bounded_before_hashing(context):
    with pytest.raises(ValueError, match="genre"):
        planner.plan_build("b", phases=["a"], game_ctx=context)


@pytest.mark.parametrize("seed", [float("nan"), 2 ** 64, True, "3"])
def test_invalid_seed_type_or_range_is_rejected(seed):
    with pytest.raises(ValueError, match="seed"):
        planner.plan_build("b", phases=["a"], seed=seed)


def test_mixed_type_dependency_keys_have_controlled_error():
    with pytest.raises(ValueError, match="keys"):
        planner.plan_build("b", phases=["a"], deps={1: [], "other": []})


def test_validator_recomputes_coverage_even_if_old_cached_flag_says_complete():
    plan = planner.plan_build("b", phases=["a", "b"], seed=3)
    assert plan["coverage"]["all_covered"]
    plan["nodes"] = [node for node in plan["nodes"] if node.get("phase_id") != "b"]
    result = planner.verify_plan(plan)
    assert not result["valid"]
    assert result["coverage_ok"] is False
    assert any("coverage" in problem for problem in result["problems"])


def test_validator_rejects_mutated_worker_and_objective_receipt():
    plan = planner.plan_build("b", phases=["a"], seed=3)
    plan["objectives"] = ["substituted objective"]
    assert not planner.verify_plan(plan)["valid"]
    assert any("receipt" in p for p in planner.verify_plan(plan)["problems"])

    plan = planner.plan_build("b", phases=["a"], seed=3)
    platoon = next(node for node in plan["nodes"] if node["tier"] == "platoon")
    platoon["workers"] = []
    verdict = planner.verify_plan(plan)
    assert not verdict["valid"]
    assert any("custody" in p for p in verdict["problems"])


def test_runtime_refuses_tampered_plan_before_invoking_executor():
    from core import swarm_scheduler as scheduler
    plan = planner.plan_build("b", phases=["a", "b"], seed=3)
    plan["objectives"] = ["tampered goal"]

    def must_not_run(*_args):
        raise AssertionError("unverified phase was executed")

    with pytest.raises(ValueError, match="unverified"):
        scheduler.run_with_executor(plan, must_not_run)


def test_game_genre_affects_receipt_even_if_workers_are_identical(monkeypatch):
    # Pin the worker RNG so the genre only changes identity, not selection.
    import random
    monkeypatch.setattr(planner, "_rng", lambda *_: random.Random(7))
    a = planner.plan_build("b", phases=["a"], game_ctx={"genre": "fantasy"})
    b = planner.plan_build("b", phases=["a"], game_ctx={"genre": "sci-fi"})
    assert a["worker_assignments"] == b["worker_assignments"]
    assert a["plan_hash"] != b["plan_hash"]

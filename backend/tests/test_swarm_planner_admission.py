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

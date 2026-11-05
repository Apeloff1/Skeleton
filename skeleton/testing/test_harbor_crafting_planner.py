"""Deterministic solver and real game replay acceptance for Lantern Quay."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import subprocess
import sys

import pytest

from skeleton.game.gameplay.harbor_crafting import (
    HarborError, canonical, decode, digest, load_source, verify_bundle,
)
from skeleton.game.gameplay.harbor_crafting_planner import solve, verify_plan

WORLD = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures" / "harbor_lantern_quay.json"


def world():
    return load_source(WORLD)


def test_solver_actually_moves_gathers_crafts_delivers_and_wins():
    plan = solve(world())
    state = verify_plan(decode(canonical(plan)))
    assert state["ending"] == "beacon"
    assert state["delivered"] is True
    ops = [action["op"] for action in plan["actions"]]
    for operation in ("move", "gather", "craft", "deliver", "choose"):
        assert operation in ops
    assert state == verify_bundle(plan["bundle"], require_win=True)
    assert state["tick"] == len(plan["actions"])


def test_solver_is_deterministic_across_independent_runs():
    assert canonical(solve(world())) == canonical(solve(world()))
    assert solve(world())["plan_digest"] == solve(world())["plan_digest"]


def test_solver_supports_both_real_choice_consequences():
    beacon = solve(world(), choice="signal")
    shelter = solve(world(), choice="shelter")
    assert verify_plan(beacon)["ending"] == "beacon"
    assert verify_plan(shelter)["ending"] == "safe_harbor"
    assert beacon["bundle"]["terminal_digest"] != shelter["bundle"]["terminal_digest"]


def test_solver_handles_finite_merchant_trading_and_multi_item_delivery():
    source = world()
    source["resources"][0]["quantity"] = 3
    source["delivery"]["ration"] = 2
    plan = solve(source)
    assert any(action["op"] == "trade" and action["item"] == "food" for action in plan["actions"])
    assert verify_plan(plan)["ending"] == "beacon"
    assert plan["bundle"]["state"]["coins"] == source["initial_coins"] - source["npc"]["price"]


def test_solver_rejects_unreachable_or_underfunded_mission():
    source = world()
    source["max_ticks"] = 3
    with pytest.raises(HarborError):
        solve(source)
    source = world()
    source["resources"][0]["quantity"] = 1
    source["npc"]["stock"] = {"food": 1}
    with pytest.raises(HarborError):
        solve(source)


@pytest.mark.parametrize("mutation", [
    lambda p: p["actions"][0].update({"direction": "west"}),
    lambda p: p["bundle"]["events"][0].update({"after": "0" * 64}),
    lambda p: p["bundle"]["state"].update({"ending": "forged"}),
    lambda p: p.update({"source_digest": "0" * 64}),
    lambda p: p.update({"plan_digest": "0" * 64}),
])
def test_tampered_plan_is_rejected(mutation):
    plan = solve(world())
    mutation(plan)
    with pytest.raises(HarborError):
        verify_plan(plan)


def test_resigning_outer_plan_does_not_override_deterministic_solver_replay():
    plan = solve(world())
    plan["actions"][0]["direction"] = "west"
    plan["plan_digest"] = digest({k: v for k, v in plan.items() if k != "plan_digest"})
    with pytest.raises(HarborError, match="replay mismatch"):
        verify_plan(plan)


def test_source_and_actions_are_not_mutated_by_solver():
    source = world()
    before = deepcopy(source)
    solve(source)
    assert source == before


def test_cli_solver_and_plan_verification_end_to_end(tmp_path):
    command = [sys.executable, "-m", "scripts.game.harbor_crafting"]
    made = subprocess.run(
        command + ["solve", "--choice", "shelter"],
        capture_output=True, check=False,
    )
    assert made.returncode == 0, made.stderr.decode()
    plan = decode(made.stdout)
    assert plan["bundle"]["state"]["ending"] == "safe_harbor"
    path = tmp_path / "plan.json"
    path.write_bytes(made.stdout)
    checked = subprocess.run(
        command + ["verify-plan", "--plan", str(path)],
        capture_output=True, check=False,
    )
    assert checked.returncode == 0, checked.stderr.decode()
    assert decode(checked.stdout)["state"]["ending"] == "safe_harbor"


def test_cli_solver_refuses_unwinnable_source_without_success(tmp_path):
    source = world()
    source["max_ticks"] = 2
    path = tmp_path / "unwinnable.json"
    path.write_bytes(canonical(source))
    command = [sys.executable, "-m", "scripts.game.harbor_crafting", "solve",
               "--source", str(path)]
    failed = subprocess.run(command, capture_output=True, check=False)
    assert failed.returncode == 2
    assert failed.stdout == b""


def test_route_solver_is_bounded_and_does_not_fabricate_wins():
    source = world()
    source["map"] = [
        "########", "#......#", "########", "#......#", "#...#..#", "########"
    ]
    source["npc"]["route"] = [[4, 1], [5, 1]]
    # The authored food deposit and dock are on the disconnected side.
    # The world is geometrically valid but no legal route reaches the cargo.
    with pytest.raises(HarborError, match="route solver"):
        solve(source)

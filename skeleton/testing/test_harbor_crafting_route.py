"""Playable route navigation: deterministic collision, replay, CLI and bounds."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import json
import subprocess
import sys

import pytest

from skeleton.game.gameplay.harbor_crafting import (
    HarborError, canonical, decode, demo_actions, digest, export_bundle, load_source,
)
from skeleton.game.gameplay.harbor_crafting_route import (
    MAX_ROUTE_NODES, MAX_ROUTE_STEPS, plan_route, verify_route,
)

WORLD = (
    Path(__file__).resolve().parents[1] / "game" / "gameplay"
    / "fixtures" / "harbor_lantern_quay.json"
)


def _root():
    return export_bundle(load_source(WORLD), [])


def _plan(root, goal, *, steps=64):
    return plan_route(
        root, goal, expected_terminal_digest=root["terminal_digest"],
        max_steps=steps,
    )


def test_route_moves_from_authored_source_and_replays_exact_save():
    root = _root()
    route = _plan(root, [2, 1])
    assert route["actions"] == [{"op": "move", "direction": "east"}]
    assert route["result"]["state"]["pos"] == [2, 1]
    assert route["result"]["events"][:len(root["events"])] == root["events"]
    assert verify_route(decode(canonical(route)))["steps"] == 1
    assert canonical(_plan(root, [2, 1])) == canonical(route)


def test_zero_length_route_preserves_save_without_new_tick():
    root = _root()
    route = _plan(root, root["state"]["pos"])
    assert route["actions"] == []
    assert route["result"] == root
    assert verify_route(route)["steps"] == 0


def test_route_after_existing_history_preserves_every_event():
    root = _root()
    partial = export_bundle(
        root["source"], [{"op": "move", "direction": "east"}]
    )
    route = _plan(partial, [1, 1])
    assert route["actions"] == [{"op": "move", "direction": "west"}]
    assert route["result"]["events"][:1] == partial["events"]
    assert verify_route(route)["terminal_digest"] == route["result"]["terminal_digest"]


@pytest.mark.parametrize("goal", [
    [0, 0], [-1, 1], [999, 1], [1, 999], [True, 1],
    ["1", 1], [1], {"x": 2, "y": 1}, None,
])
def test_bad_or_blocked_goals_are_rejected(goal):
    with pytest.raises(HarborError):
        _plan(_root(), goal)


@pytest.mark.parametrize("budget", [0, -1, True, 65, 1.0, "5"])
def test_invalid_budgets_fail_closed(budget):
    with pytest.raises(HarborError):
        _plan(_root(), [2, 1], steps=budget)


def test_insufficient_route_budget_fails_without_partial_save():
    root = _root()
    with pytest.raises(HarborError, match="route unavailable"):
        _plan(root, [5, 3], steps=1)
    assert root["state"]["tick"] == 0


def test_stale_checkpoint_lease_rejected():
    root = _root()
    with pytest.raises(HarborError, match="stale route checkpoint"):
        plan_route(root, [2, 1], expected_terminal_digest="0" * 64)


def test_forged_path_rejected_even_when_outer_digest_resealed():
    original = _plan(_root(), [2, 1])
    for change in ("actions", "result", "explored", "goal"):
        forged = deepcopy(original)
        if change == "actions":
            forged["actions"] = [{"op": "wait"}]
        elif change == "result":
            forged["result"]["state"]["coins"] = 999
        elif change == "explored":
            forged["explored"] += 1
        else:
            forged["goal"] = [1, 1]
        forged["route_digest"] = digest({
            key: value for key, value in forged.items()
            if key != "route_digest"
        })
        with pytest.raises(HarborError):
            verify_route(forged)


def test_route_does_not_mutate_untrusted_input():
    root = _root()
    snapshot = deepcopy(root)
    _plan(root, [2, 1])
    assert root == snapshot


def test_navigation_budgets_are_explicit_and_finite():
    assert MAX_ROUTE_STEPS <= 64
    assert MAX_ROUTE_NODES <= 8192


def test_cli_route_plan_and_verify_portable_artifact(tmp_path):
    root = _root()
    root_path = tmp_path / "root.json"
    root_path.write_bytes(canonical(root))
    base = [sys.executable, "-m", "scripts.game.harbor_crafting"]
    planned = subprocess.run(
        base + [
            "route-plan", "--bundle", str(root_path), "--goal", "2,1",
            "--expected-terminal-digest", root["terminal_digest"],
        ], capture_output=True, text=True, timeout=30,
    )
    assert planned.returncode == 0, planned.stderr
    route = json.loads(planned.stdout)
    assert route["result"]["state"]["pos"] == [2, 1]
    route_path = tmp_path / "route.json"
    route_path.write_text(planned.stdout, encoding="utf-8")
    verified = subprocess.run(
        base + ["route-verify", "--route", str(route_path)],
        capture_output=True, text=True, timeout=30,
    )
    assert verified.returncode == 0, verified.stderr
    assert json.loads(verified.stdout)["steps"] == 1


def test_cli_rejects_malformed_goal_and_stale_lease(tmp_path):
    root = _root()
    root_path = tmp_path / "root.json"
    root_path.write_bytes(canonical(root))
    base = [sys.executable, "-m", "scripts.game.harbor_crafting"]
    for goal, lease in [("1,x", root["terminal_digest"]), ("2,1", "stale")]:
        result = subprocess.run(
            base + [
                "route-plan", "--bundle", str(root_path), "--goal", goal,
                "--expected-terminal-digest", lease,
            ], capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 2
        assert not result.stdout


def test_npc_collision_requires_wait_before_entering_occupied_tile():
    world = load_source(WORLD)
    world["npc"]["route"] = [[2, 1], [3, 1]]
    root = export_bundle(world, [])
    route = _plan(root, [2, 1])
    assert route["actions"] == [
        {"op": "wait"}, {"op": "move", "direction": "east"},
    ]
    assert verify_route(route)["steps"] == 2


def test_route_rejects_post_victory_navigation():
    world = load_source(WORLD)
    won = export_bundle(world, demo_actions(), require_win=True)
    with pytest.raises(HarborError, match="after ending"):
        _plan(won, [2, 1])

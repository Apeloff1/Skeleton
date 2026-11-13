"""Bounded convoy planner: actual craft, escort, tactical combat and earned victory."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import subprocess
import sys

import pytest

from skeleton.game.gameplay.harbor_crafting import (
    HarborError, canonical, decode, digest, load_source,
)
from skeleton.game.gameplay.harbor_crafting_convoy import build_convoy
from skeleton.game.gameplay.harbor_crafting_convoy_solver import (
    solve_convoy, verify_convoy_plan,
)

FIXTURES = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures"
CLI = [sys.executable, "-m", "skeleton.game.gameplay.harbor_crafting_cli"]


def inputs():
    world = load_source(FIXTURES / "harbor_lantern_quay.json")
    board = decode((FIXTURES / "harbor_lantern_quay_convoy.json").read_bytes())
    return world, board


def test_solver_authors_real_crafting_and_combat_actions():
    world, board = inputs()
    plan = solve_convoy(world, board)
    assert plan["report"]["state"]["complete"]
    assert plan["report"]["state"]["bounty"] == 7
    assert any(action == {"op": "craft", "recipe": "lantern"} for action in plan["actions"])
    assert sum(action["op"] == "escort" for action in plan["actions"]) == 4
    assert sum(action["op"] == "strike" for action in plan["actions"]) == 1
    assert build_convoy(world, board, plan["actions"], require_complete=True) == plan["report"]
    assert verify_convoy_plan(decode(canonical(plan)))["complete"]


def test_solver_fails_closed_when_authored_enemy_needs_unobtainable_weapon():
    world, board = inputs()
    impossible = deepcopy(board)
    impossible["encounters"][0]["strength"] = 2
    with pytest.raises(HarborError):
        solve_convoy(world, impossible)


def test_solver_resealed_actions_or_rewards_cannot_claim_victory():
    world, board = inputs()
    plan = solve_convoy(world, board)
    forged = deepcopy(plan)
    forged["actions"][-1] = {"op": "wait"}
    forged["plan_digest"] = digest({
        key: value for key, value in forged.items() if key != "plan_digest"
    })
    with pytest.raises(HarborError, match="replay"):
        verify_convoy_plan(forged)


def test_solver_cli_generates_and_verifies_real_game_plan(tmp_path):
    world, board = inputs()
    def call(*args):
        proc = subprocess.run(CLI + list(args), capture_output=True, check=False)
        assert proc.returncode == 0, proc.stderr.decode()
        return decode(proc.stdout)
    plan = call(
        "convoy-solve",
        "--source", str(FIXTURES / "harbor_lantern_quay.json"),
        "--convoy-board", str(FIXTURES / "harbor_lantern_quay_convoy.json"),
    )
    file = tmp_path / "plan.json"
    file.write_bytes(canonical(plan))
    result = call("convoy-verify-plan", "--convoy-plan", str(file))
    assert result["verified"] and result["bounty"] == 7

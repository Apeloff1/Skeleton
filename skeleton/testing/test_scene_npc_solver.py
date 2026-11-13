"""NPC shortest-route solver: real movement, earned choices and replay."""
import copy
import json

import pytest

from skeleton.game.gameplay.scene_npc_encounter import (
    original_encounter, simulate_encounter,
)
from skeleton.game.gameplay.scene_npc_solver import (
    cli, solve_encounter, verify_solution,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_solver_plays_original_to_authored_rescue():
    result = solve_encounter(original_encounter(), "rescued")
    assert result["session"]["state"]["phase"] == "finished"
    assert result["session"]["state"]["ending"] == "rescued"
    assert result["session"]["state"]["flags"] == ["keeper_trust"]
    assert len(result["actions"]) <= 8
    assert result["session"] == simulate_encounter(
        original_encounter(), result["actions"],
    )
    assert verify_solution(json.loads(json.dumps(result))) == result


def test_alternate_ending_has_distinct_earned_route():
    result = solve_encounter(original_encounter(), "lost")
    assert result["session"]["state"]["scene"]["state"]["phase"] == "lost"
    assert result["session"]["state"]["ending"] == "lost"
    assert verify_solution(result) == result


def test_solver_respects_search_budget_and_authored_target():
    with pytest.raises(SceneTravelError, match="not authored"):
        solve_encounter(original_encounter(), "nonexistent")
    with pytest.raises(SceneTravelError, match="node budget"):
        solve_encounter(original_encounter(), "rescued", max_nodes=1)
    with pytest.raises(SceneTravelError, match="unreachable"):
        solve_encounter(original_encounter(), "rescued", max_depth=1)
    with pytest.raises(SceneTravelError, match="max_nodes"):
        solve_encounter(original_encounter(), "rescued", max_nodes=True)


@pytest.mark.parametrize("mutation", [
    lambda x: x.update(source_digest="0" * 64),
    lambda x: x.update(ending_id="solo"),
    lambda x: x.update(explored_nodes=0),
    lambda x: x["actions"][0].update(offer_id="decline"),
    lambda x: x["session"]["state"].update(phase="blocked"),
    lambda x: x.update(receipt="0" * 64),
])
def test_forged_solver_witness_rejected(mutation):
    receipt = solve_encounter(original_encounter(), "rescued")
    bad = copy.deepcopy(receipt)
    mutation(bad)
    with pytest.raises(SceneTravelError):
        verify_solution(bad)


def test_cli_is_reachable_and_returns_nonzero_on_bad_source(capsys):
    from skeleton.__main__ import main
    assert main(["scene-npc-solve", "demo"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["session"]["state"]["ending"] == "rescued"
    assert cli(["verify", "--receipt-json", json.dumps(receipt)]) == 0
    assert json.loads(capsys.readouterr().out) == receipt
    assert cli(["solve", "--source-json", '{"bad":true}',
                "--ending-id", "rescued"]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False

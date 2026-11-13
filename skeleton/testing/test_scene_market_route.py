"""Focused acceptance for source-bound market search and player board."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_market import (
    export_market, import_market, new_market, original_market, resume_market,
    simulate_market,
)
from skeleton.game.gameplay.scene_market_board import (
    market_board, verify_market_board,
)
from skeleton.game.gameplay.scene_market_route import (
    _choices, cli, solve_market_route, verify_market_route,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_route_replays_into_real_earned_market_victory():
    source, _ = original_market()
    start = new_market(source)
    report = solve_market_route(start, max_nodes=4096, max_depth=40)
    assert report["status"] == "proven_win"
    assert report["action_count"] > 0
    assert verify_market_route(start, report) == report
    final = resume_market(start, report["actions"])
    assert final["state"]["phase"] == "won"
    assert final["state"]["reputation"] == 5
    assert final["state"]["delivered"] == ["sanctuary_seal"]
    assert final["state"]["goods"] == {}
    assert import_market(export_market(final)) == final
    assert report["terminal_state_digest"] == final["state_digest"]


def test_route_from_middle_checkpoint_replay_and_lineage():
    source, actions = original_market()
    middle = simulate_market(source, actions[:5])
    untouched = copy.deepcopy(middle)
    report = solve_market_route(middle, max_nodes=4096, max_depth=40)
    assert report["status"] == "proven_win"
    assert resume_market(middle, report["actions"])["state"]["phase"] == "won"
    assert verify_market_route(middle, report) == report
    assert middle == untouched
    with pytest.raises(SceneTravelError, match="does not match"):
        verify_market_route(new_market(source), report)


def test_terminal_win_empty_witness_and_loss_inconclusive():
    source, actions = original_market()
    won = simulate_market(source, actions)
    report = solve_market_route(won)
    assert report["status"] == "proven_win"
    assert report["actions"] == []
    assert verify_market_route(won, report) == report
    lost = simulate_market(
        source, [a for a in actions if a.get("kind") != "deliver"],
    )
    assert lost["state"]["phase"] == "lost"
    no_route = solve_market_route(lost)
    assert no_route["status"] == "inconclusive"
    assert no_route["reason"] == "terminal_checkpoint"


@pytest.mark.parametrize("nodes,depth", [
    (0, 10), (4097, 10), (True, 10), (5, -1), (5, 65),
    (5, True), ("5", 10),
])
def test_search_budgets_fail_closed(nodes, depth):
    source, _ = original_market()
    with pytest.raises(SceneTravelError):
        solve_market_route(new_market(source), max_nodes=nodes, max_depth=depth)


def test_zero_depth_never_mislabels_impossible():
    source, _ = original_market()
    report = solve_market_route(new_market(source), max_depth=0)
    assert report["status"] == "inconclusive"
    assert report["reason"] == "depth_budget_exhausted"
    assert report["actions"] == []


def test_forged_route_even_rechecksummed_is_rejected():
    source, _ = original_market()
    start = new_market(source)
    report = solve_market_route(start, max_nodes=4096, max_depth=40)
    tampered = copy.deepcopy(report)
    tampered["actions"][0] = {"kind": "buy", "offer_id": "copper_badge"}
    tampered["checksum"] = dig({
        k: v for k, v in tampered.items() if k != "checksum"
    })
    with pytest.raises(SceneTravelError):
        verify_market_route(start, tampered)


def test_board_is_read_only_and_exact_checkpoint_bound():
    source, actions = original_market()
    partial = simulate_market(source, actions[:5])
    snapshot = copy.deepcopy(partial)
    board = market_board(partial, hint_nodes=4096, hint_depth=40)
    assert board["credits"] == 3
    assert board["hint_status"] == "proven_win"
    assert board["hint_action"] is not None
    assert verify_market_board(partial, board) == board
    assert partial == snapshot
    bad = copy.deepcopy(board)
    bad["credits"] = 900
    bad["checksum"] = dig({k: v for k, v in bad.items() if k != "checksum"})
    with pytest.raises(SceneTravelError):
        verify_market_board(partial, bad)


def test_market_candidates_cannot_grant_goods_or_teleport():
    source, _ = original_market()
    initial = new_market(source)
    choices = _choices(initial)
    assert all(a["kind"] == "tile" for a in choices)
    assert all(a["action"]["kind"] != "travel" for a in choices)
    assert all(a["action"]["kind"] != "collect" for a in choices)


def test_user_reachable_route_and_board_commands(capsys):
    from skeleton.__main__ import main
    assert main(["scene-market-route", "demo", "--max-nodes", "4096",
                 "--max-depth", "40"]) == 0
    route = json.loads(capsys.readouterr().out)
    assert route["status"] == "proven_win"
    assert main(["scene-market-board", "demo", "--hint-nodes", "4096",
                 "--hint-depth", "40"]) == 0
    board = json.loads(capsys.readouterr().out)
    assert board["hint_status"] == "proven_win"
    assert cli(["solve", "--session-json", '{"bad":1}']) == 2
    assert "error" in json.loads(capsys.readouterr().err)


def test_tampered_source_and_checkpoint_never_receive_route():
    source, _ = original_market()
    bad = new_market(source)
    bad["state"]["credits"] = 999
    with pytest.raises(SceneTravelError):
        solve_market_route(bad)
    source["coin_pickups"][0]["amount"] = 0
    with pytest.raises(SceneTravelError):
        new_market(source)

"""Cooperative market route witnesses: roles, boundedness and replay custody."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.scene_market_party import (
    _advance, new_party, original_party, simulate_party,
)
from skeleton.game.gameplay.scene_market_party_route import (
    _candidate_turns, cli, solve_party_route, verify_party_route,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_original_party_hint_is_a_canonical_victory_witness():
    source, turns = original_party()
    initial = new_party(source)
    proof = solve_party_route(initial, hint_turns=turns)
    assert proof["status"] == "proven_win"
    assert proof["turns"] == turns
    assert proof["turn_count"] == len(turns)
    assert proof["terminal_state_digest"] == simulate_party(source, turns)["state_digest"]
    assert verify_party_route(initial, json.loads(json.dumps(proof))) == proof


def test_partial_checkpoint_route_preserves_earned_progress():
    source, turns = original_party()
    split = len(turns) // 2
    checkpoint = simulate_party(source, turns[:split])
    proof = solve_party_route(checkpoint, hint_turns=turns[split:])
    assert proof["status"] == "proven_win"
    assert proof["initial_state_digest"] == checkpoint["state_digest"]
    assert proof["turn_count"] == len(turns) - split
    assert verify_party_route(checkpoint, proof) == proof


def test_search_miss_is_inconclusive_not_unwinnable():
    source, _ = original_party()
    proof = solve_party_route(new_party(source), max_nodes=1, max_depth=0)
    assert proof["status"] == "inconclusive"
    assert proof["turns"] == []
    assert proof["terminal_state_digest"] is None
    assert verify_party_route(new_party(source), proof) == proof


def test_candidate_turns_are_role_gated_and_canonical():
    source, _ = original_party()
    session = new_party(source)
    options = _candidate_turns(session)
    assert options[0] == {"player_id": "rowan", "action": {"kind": "pass"}}
    assert all(turn["player_id"] == "rowan" for turn in options)
    assert all(turn["action"]["kind"] in ("pass", "tile", "buy")
               for turn in options)
    for turn in options:
        try:
            _advance(session, turn)
        except SceneTravelError:
            # Candidate enumeration does not assert canonical legality.
            pass


@pytest.mark.parametrize("nodes,depth", [(0, 4), (1025, 4), (True, 4),
                                        (1, -1), (1, 65), (1, True)])
def test_search_budgets_are_strict(nodes, depth):
    source, _ = original_party()
    with pytest.raises(SceneTravelError):
        solve_party_route(new_party(source), max_nodes=nodes, max_depth=depth)


def test_invalid_hint_never_becomes_witness():
    source, turns = original_party()
    invalid = copy.deepcopy(turns)
    invalid[0]["player_id"] = "forged"
    with pytest.raises(SceneTravelError):
        solve_party_route(new_party(source), hint_turns=invalid)
    with pytest.raises(SceneTravelError):
        solve_party_route(new_party(source), hint_turns=turns, max_depth=0)


@pytest.mark.parametrize("mutation", [
    lambda r: r.update(status="inconclusive"),
    lambda r: r.update(source_digest="0" * 64),
    lambda r: r.update(terminal_state_digest="0" * 64),
    lambda r: r.update(portable_checksum="0" * 64),
    lambda r: r.update(explored_states=999),
    lambda r: r["turns"][0].update(player_id="forged"),
])
def test_forged_witness_rejected_even_with_recomputed_checksum(mutation):
    from skeleton.game.gameplay.flgb_gameplay_runtime import dig
    source, turns = original_party()
    first = new_party(source)
    original = solve_party_route(first, hint_turns=turns)
    forged = copy.deepcopy(original)
    mutation(forged)
    # Every parameter must change signed-over data, not only a digest
    # that this test immediately recomputes.
    assert forged != original
    forged["checksum"] = dig({k: v for k, v in forged.items() if k != "checksum"})
    with pytest.raises(SceneTravelError):
        verify_party_route(first, forged)


def test_invalid_outer_checksum_is_rejected_without_recomputation():
    source, turns = original_party()
    initial = new_party(source)
    forged = solve_party_route(initial, hint_turns=turns)
    assert forged["checksum"] != "0" * 64
    forged["checksum"] = "0" * 64
    with pytest.raises(SceneTravelError):
        verify_party_route(initial, forged)


def test_cli_demo_and_main_dispatch(capsys):
    from skeleton.__main__ import main
    assert main(["scene-market-party-route", "demo"]) == 0
    proof = json.loads(capsys.readouterr().out)
    assert proof["status"] == "proven_win"
    assert cli(["solve", "--session-json", "{}"]) == 2
    assert "error" in json.loads(capsys.readouterr().err)

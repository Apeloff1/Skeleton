"""Interactive capture bounty with deterministic AI and safe resume."""
from __future__ import annotations

import copy
import io
import json

import pytest

from skeleton.__main__ import main
from skeleton.game.gameplay.arena_control_contracts import (
    original_contract, verify_contract,
)
from skeleton.game.gameplay.arena_control_contracts_interactive import (
    play_contract_interactive, verify_interactive_receipt,
)
from skeleton.game.gameplay.turn_combat import CombatSessionError


def test_player_input_and_opponent_ai_produce_real_replayable_contract():
    inputs = io.StringIO(
        '{"kind":"move","actor_id":"scout","direction":"east"}\n'
        '{"kind":"guard","actor_id":"scout"}\n'
    )
    out = io.StringIO()
    receipt = play_contract_interactive(original_contract(), "wayfarers",
                                        input_stream=inputs, output_stream=out)
    events = [json.loads(line) for line in out.getvalue().splitlines()]
    assert any(event["type"] == "player_turn" for event in events)
    assert any(event["type"] == "opponent_action" for event in events)
    assert events[-1]["type"] == "contract_result"
    assert verify_interactive_receipt(json.loads(json.dumps(receipt))) == receipt
    assert verify_contract(receipt["contract_session"]) == receipt["contract_session"]


def test_eof_returns_verifiable_zero_reward_checkpoint():
    out = io.StringIO()
    receipt = play_contract_interactive(original_contract(), "wayfarers",
                                        input_stream=io.StringIO(""),
                                        output_stream=out)
    assert receipt["status"] == "checkpoint"
    assert receipt["reason"] == "input_eof"
    assert receipt["contract_session"]["state"]["reward"] == 0
    assert verify_interactive_receipt(receipt) == receipt


def test_invalid_actor_cannot_move_opponent_or_mint_reward():
    out = io.StringIO()
    receipt = play_contract_interactive(
        original_contract(), "wayfarers",
        input_stream=io.StringIO('{"kind":"guard","actor_id":"warden"}\n'),
        output_stream=out)
    assert receipt["status"] == "rejected"
    assert receipt["contract_session"]["state"]["tick"] == 0
    assert receipt["contract_session"]["state"]["reward"] == 0
    assert verify_interactive_receipt(receipt) == receipt


def test_resume_from_eof_matches_direct_canonical_replay():
    source = original_contract()
    first = play_contract_interactive(
        source, "wayfarers", input_stream=io.StringIO(""),
        output_stream=io.StringIO())
    resumed = play_contract_interactive(
        source, "wayfarers", resume=first["contract_session"],
        input_stream=io.StringIO('{"kind":"move","actor_id":"scout","direction":"east"}\n'),
        output_stream=io.StringIO())
    assert resumed["contract_session"]["state"]["tick"] >= 1
    assert verify_interactive_receipt(resumed) == resumed


@pytest.mark.parametrize("mutate", [
    lambda r: r["contract_session"]["state"].update(reward=9999),
    lambda r: r["source_digest"] = "bad",
    lambda r: r["team"] = "opponent",
    lambda r: r["status"] = "completed",
])
def test_tampered_receipt_fails_closed(mutate):
    receipt = play_contract_interactive(
        original_contract(), "wayfarers", input_stream=io.StringIO(""),
        output_stream=io.StringIO())
    bad = copy.deepcopy(receipt)
    mutate(bad)
    with pytest.raises(CombatSessionError):
        verify_interactive_receipt(bad)


def test_reject_unknown_team_and_source_mismatch():
    with pytest.raises(CombatSessionError):
        play_contract_interactive(original_contract(), "reedbound",
                                  input_stream=io.StringIO(""),
                                  output_stream=io.StringIO())
    first = play_contract_interactive(
        original_contract(), "wayfarers", input_stream=io.StringIO(""),
        output_stream=io.StringIO())
    source = original_contract()
    source["objectives"][0]["reward"] += 1
    with pytest.raises(CombatSessionError, match="source mismatch"):
        play_contract_interactive(source, "wayfarers",
                                  resume=first["contract_session"],
                                  input_stream=io.StringIO(""),
                                  output_stream=io.StringIO())


def test_installed_cli_verify_interactive_receipt(capsys):
    receipt = play_contract_interactive(
        original_contract(), "wayfarers", input_stream=io.StringIO(""),
        output_stream=io.StringIO())
    assert main(["arena-control-contracts-play", "verify",
                 "--receipt-json", json.dumps(receipt)]) == 0
    assert json.loads(capsys.readouterr().out) == receipt

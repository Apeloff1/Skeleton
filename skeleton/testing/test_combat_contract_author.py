"""Transactional contract authoring and interactive end-to-end gameplay."""
from __future__ import annotations

import copy
import io
import json

import pytest

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import CombatSessionError, original_demo
from skeleton.game.gameplay.combat_contract import (
    demo_contract, normalize_contract, original_contract, verify_contract,
)
from skeleton.game.gameplay.combat_contract_author import (
    author_contract, cli, demo_author, verify_author_report,
)
from skeleton.game.gameplay.combat_contract_interactive import play_contract


def test_transactional_edit_changes_reward_and_previews_earned_victory():
    report = demo_author()
    assert report["after"]["reward"]["credits"] == 24
    assert report["preview"]["state"]["phase"] == "won"
    assert report["preview"]["state"]["credits"] == 24
    assert verify_author_report(json.loads(json.dumps(report))) == report


def test_author_lease_fails_closed_without_mutating_source():
    source = original_contract()
    frozen = copy.deepcopy(source)
    with pytest.raises(CombatSessionError, match="lease"):
        author_contract(source, [{"kind": "set_reward", "credits": 50,
                                  "item_id": "new"}], "0" * 64)
    assert source == frozen


def test_author_adds_guard_gate_and_preview_does_not_fake_reward():
    source = original_contract()
    _, actions = original_demo()
    report = author_contract(
        source,
        [{"kind": "add_objective", "objective": {
            "id": "protect", "kind": "guard", "minimum": 1,
        }}],
        dig(normalize_contract(source)), preview_actions=actions,
    )
    assert report["preview"]["state"]["phase"] == "failed"
    assert report["preview"]["state"]["credits"] == 0
    assert verify_author_report(report) == report


@pytest.mark.parametrize("edits", [
    [{"kind": "remove_objective", "objective_id": "missing"}],
    [{"kind": "add_objective", "objective": {
        "id": "defeat_warden", "kind": "guard", "minimum": 1}}],
    [{"kind": "set_reward", "credits": True, "item_id": "bad"}],
    [{"kind": "set_player_team", "team": "outsiders"}],
    [{"kind": "remove_objective", "objective_id": "defeat_warden"},
     {"kind": "remove_objective", "objective_id": "swift_resolution"}],
    [{"kind": "set_reward", "credits": 14, "item_id": "bridge_pass"}],
    [{"kind": "set_reward", "credits": 1, "item_id": "a", "extra": True}],
])
def test_invalid_author_edits_are_atomic(edits):
    source = original_contract()
    before = copy.deepcopy(source)
    with pytest.raises(CombatSessionError):
        author_contract(source, edits, dig(normalize_contract(source)))
    assert source == before


@pytest.mark.parametrize("mutate", [
    lambda r: r["after"]["reward"].update(credits=1000),
    lambda r: r["preview"]["state"].update(credits=999),
    lambda r: r["edits"][0].update(credits=100),
    lambda r: r.update(receipt="0" * 64),
])
def test_author_report_tamper_rejected(mutate):
    report = copy.deepcopy(demo_author())
    mutate(report)
    with pytest.raises(CombatSessionError):
        verify_author_report(report)


def test_manual_interactive_contract_matches_batch_replay():
    _, actions = original_demo()
    reader = io.StringIO("".join(json.dumps(a) + "\n" for a in actions))
    writer = io.StringIO()
    saved = play_contract(original_contract(), auto_opponents=False,
                          input_stream=reader, output_stream=writer)
    assert saved == demo_contract()
    assert verify_contract(saved) == saved
    events = [json.loads(line) for line in writer.getvalue().splitlines()]
    assert sum(event["event"] == "turn" for event in events) == 3
    assert events[-1]["event"] == "contract_terminal"
    assert events[-1]["earned_inventory"] == {"bridge_pass": 1}


def test_interactive_eof_fails_closed_and_does_not_award_rewards():
    with pytest.raises(CombatSessionError, match="input ended"):
        play_contract(original_contract(), auto_opponents=False,
                      input_stream=io.StringIO(""),
                      output_stream=io.StringIO())


def test_interactive_source_mismatch_and_terminal_resume_denied():
    saved = demo_contract()
    with pytest.raises(CombatSessionError, match="terminal"):
        play_contract(original_contract(), resume=saved,
                      input_stream=io.StringIO(""), output_stream=io.StringIO())
    changed = original_contract()
    changed["reward"]["credits"] = 1
    with pytest.raises(CombatSessionError, match="source mismatch"):
        play_contract(changed, resume=saved,
                      input_stream=io.StringIO(""), output_stream=io.StringIO())


def test_author_cli_is_reachable_and_replays_report(capsys):
    from skeleton.__main__ import main
    assert main(["combat-contract-author", "demo"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert cli(["verify", "--report-json", json.dumps(report)]) == 0
    assert json.loads(capsys.readouterr().out) == report
    assert main(["combat-contract-author", "run",
                 "--source-json", "{}", "--edits-json", "[]",
                 "--expected-digest", "0" * 64]) == 2

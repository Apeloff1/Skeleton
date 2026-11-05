"""Real interactive quest: NPC schedules, crafting, combat, recovery and replay."""
from __future__ import annotations

import io
import json

import pytest

from skeleton.game.gameplay.expedition_quest import (
    demo_actions, import_quest, new_quest, original_quest, simulate_quest,
    verify_quest,
)
from skeleton.game.gameplay.expedition_quest_interactive import (
    cli, legal_quest_actions, parse_quest_action, play_quest,
)
from skeleton.game.gameplay.turn_combat import CombatSessionError


def _events(writer):
    return [json.loads(line) for line in writer.getvalue().splitlines()]


def _demo_input():
    return io.StringIO(
        "talk guide aid\ntravel forge\ntalk smith aid\ncraft beacon\n"
        "travel dock\ntravel camp\nfight\nbuy tide_tonic\n"
        "use tide_tonic\nfight\nfinish beacon_lit\n"
    )


def test_playable_quest_reaches_earned_crafting_combat_ending():
    writer = io.StringIO()
    result = play_quest(original_quest(), input_stream=_demo_input(),
                        output_stream=writer, checkpoint_every=3)
    assert result == simulate_quest(original_quest(), demo_actions())
    events = _events(writer)
    assert len([e for e in events if e["event"] == "accepted"]) == 11
    assert events[-1]["ending"] == "beacon_lit"
    assert import_quest(events[-1]["bundle"]) == result
    assert any(e["event"] == "checkpoint" and e["reason"] == "interval" for e in events)


def test_legal_moves_follow_npc_schedule_and_real_inventory():
    start = new_quest(original_quest())
    options = legal_quest_actions(start)
    assert {"kind": "talk", "npc_id": "guide", "decision": "aid"} in options
    assert {"kind": "craft", "recipe_id": "beacon"} not in options
    assert {"kind": "expedition", "action": {"kind": "fight"}} not in options


def test_eof_emits_recoverable_checkpoint_without_free_items():
    writer = io.StringIO()
    with pytest.raises(CombatSessionError, match="input ended"):
        play_quest(original_quest(), input_stream=io.StringIO("talk guide aid\n"),
                   output_stream=writer)
    checkpoint = [e for e in _events(writer) if e["event"] == "checkpoint"][-1]
    assert checkpoint["reason"] == "input_eof"
    saved = verify_quest(checkpoint["session"])
    assert saved["state"]["items"] == {"reed": 1}
    remaining = io.StringIO(
        "travel forge\ntalk smith aid\ncraft beacon\ntravel dock\ntravel camp\n"
        "fight\nbuy tide_tonic\nuse tide_tonic\nfight\nfinish beacon_lit\n"
    )
    assert play_quest(session=saved, input_stream=remaining,
                      output_stream=io.StringIO()) == simulate_quest(
                          original_quest(), demo_actions())


def test_three_invalid_actions_do_not_mutate_quest():
    writer = io.StringIO()
    with pytest.raises(CombatSessionError, match="retries exhausted"):
        play_quest(original_quest(), input_stream=io.StringIO(
            "craft beacon\nfinish beacon_lit\ntravel nowhere\n"
        ), output_stream=writer)
    events = _events(writer)
    assert len([e for e in events if e["event"] == "invalid"]) == 3
    saved = [e for e in events if e["event"] == "checkpoint"][-1]["session"]
    assert saved == new_quest(original_quest())


def test_turn_budget_checkpoints_accepted_prefix():
    writer = io.StringIO()
    with pytest.raises(CombatSessionError, match="budget exhausted"):
        play_quest(original_quest(), input_stream=_demo_input(),
                   output_stream=writer, max_turns=1)
    checkpoint = [e for e in _events(writer) if e["event"] == "checkpoint"][-1]
    assert checkpoint["reason"] == "turn_budget"
    assert checkpoint["session"]["state"]["tick"] == 1


def test_wrong_trusted_source_digest_rejected_before_output():
    writer = io.StringIO()
    with pytest.raises(CombatSessionError, match="trusted source"):
        play_quest(original_quest(), expected_source_digest="0" * 64,
                   input_stream=_demo_input(), output_stream=writer)
    assert writer.getvalue() == ""


@pytest.mark.parametrize("line", [
    "", "talk guide", "craft", "finish", "buy", "travel a b",
    '{"kind":"travel","kind":"finish"}',
    '{"kind":"travel","to":NaN}',
    "x" * (128 * 1024 + 1),
])
def test_malformed_input_fails_closed(line):
    with pytest.raises(CombatSessionError):
        parse_quest_action(line)


def test_cli_reaches_canonical_app(capsys, monkeypatch):
    from skeleton.__main__ import main
    monkeypatch.setattr("sys.stdin", _demo_input())
    assert main(["quest-expedition-play", "--demo", "--checkpoint-every", "3"]) == 0
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert events[-1]["ending"] == "beacon_lit"


def test_cli_rejects_duplicate_json_keys(capsys):
    assert cli(["--source-json", '{"x":1,"x":2}']) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False

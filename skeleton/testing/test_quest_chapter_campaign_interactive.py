"""Interactive campaign input cannot bypass authored quest and reward gates."""
from __future__ import annotations

import io
import json

import pytest

from skeleton.game.gameplay.quest_chapter_campaign import (
    demo_campaign_actions, original_campaign, simulate_campaign,
)
from skeleton.game.gameplay.quest_chapter_campaign_interactive import (
    cli, legal_campaign_actions, parse_campaign_action, play_campaign,
)
from skeleton.game.gameplay.turn_combat import CombatSessionError


def near_terminal():
    return simulate_campaign(original_campaign(), demo_campaign_actions()[:-2])


def events(text):
    return [json.loads(line) for line in text.splitlines()]


def test_interactive_checkpoint_to_victory_replays_and_exports_exact_save():
    checkpoint = near_terminal()
    writer = io.StringIO()
    final = play_campaign(
        session=checkpoint, input_stream=io.StringIO("finish beacon_lit\nadvance\n"),
        output_stream=writer, checkpoint_every=1, max_turns=2,
    )
    assert final == simulate_campaign(original_campaign(), demo_campaign_actions())
    output = events(writer.getvalue())
    assert [e["event"] for e in output].count("accepted") == 2
    assert output[-1]["event"] == "terminal"
    assert output[-1]["bundle"]["session"] == final
    assert output[-2]["event"] == "checkpoint"
    assert output[-2]["reason"] == "terminal"


def test_only_finished_quest_can_advance_and_rewards_are_not_client_grants():
    fresh = simulate_campaign(original_campaign(), [])
    assert {"kind": "advance"} not in legal_campaign_actions(fresh)
    with pytest.raises(CombatSessionError):
        parse_campaign_action('{"kind":"grant","flag":"harbor_secured"}')
    with pytest.raises(CombatSessionError):
        parse_campaign_action('{"kind":"advance","extra":true}')


def test_eof_preserves_last_valid_checkpoint_without_fake_terminal():
    checkpoint = near_terminal()
    writer = io.StringIO()
    with pytest.raises(CombatSessionError, match="checkpoint emitted"):
        play_campaign(session=checkpoint, input_stream=io.StringIO(""),
                      output_stream=writer)
    output = events(writer.getvalue())
    assert output[-1]["event"] == "checkpoint"
    assert output[-1]["reason"] == "input_eof"
    assert output[-1]["session"] == checkpoint


def test_three_invalid_actions_fail_closed_without_advancing_state():
    checkpoint = near_terminal()
    writer = io.StringIO()
    with pytest.raises(CombatSessionError, match="retries exhausted"):
        play_campaign(
            session=checkpoint, input_stream=io.StringIO("advance\nadvance\nadvance\n"),
            output_stream=writer,
        )
    output = events(writer.getvalue())
    assert len([e for e in output if e["event"] == "invalid"]) == 3
    assert output[-1]["session"] == checkpoint


@pytest.mark.parametrize("kwargs", [
    {"checkpoint_every": 0}, {"checkpoint_every": True},
    {"checkpoint_every": 65}, {"max_turns": 0},
    {"max_turns": True}, {"max_turns": 97},
    {"expected_source_digest": "0" * 64},
])
def test_invalid_play_configuration_rejected(kwargs):
    with pytest.raises(CombatSessionError):
        play_campaign(
            session=near_terminal(), input_stream=io.StringIO(""),
            output_stream=io.StringIO(), **kwargs,
        )


def test_source_bound_parser_and_json_reject_hostile_input():
    assert parse_campaign_action("advance") == {"kind": "advance"}
    assert parse_campaign_action("finish beacon_lit") == {
        "kind": "quest", "action": {"kind": "finish", "ending_id": "beacon_lit"},
    }
    with pytest.raises(CombatSessionError):
        parse_campaign_action("x" * (128 * 1024 + 1))
    with pytest.raises(CombatSessionError):
        parse_campaign_action('{"kind":"advance","kind":"quest"}')


def test_installed_cli_resumes_replayable_campaign(capsys, monkeypatch):
    from skeleton.__main__ import main
    checkpoint = near_terminal()
    monkeypatch.setattr("sys.stdin", io.StringIO("finish beacon_lit\nadvance\n"))
    assert main(["quest-campaign-play", "--resume-json", json.dumps(checkpoint),
                 "--max-turns", "2"]) == 0
    output = events(capsys.readouterr().out)
    assert output[-1]["phase"] == "won"
    assert output[-1]["bundle"]["session"]["state"]["flags"] == [
        "beacon_raised", "harbor_secured",
    ]


def test_cli_rejects_invalid_save(capsys):
    assert cli(["--resume-json", '{"bad":true}']) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False

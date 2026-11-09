"""Interactive source-bound faction quest, input, checkpoints and export."""
from __future__ import annotations

import copy
import io
import json

import pytest

from skeleton.game.gameplay.expedition_quest import demo_actions
from skeleton.game.gameplay.quest_factions import (
    export_factions, import_factions, original_factions, resume_factions,
    simulate_factions, verify_factions,
)
from skeleton.game.gameplay.quest_factions_interactive import (
    cli, legal_faction_actions, play_factions,
)
from skeleton.game.gameplay.turn_combat import CombatSessionError


def _stream(actions):
    return io.StringIO("".join(
        json.dumps({"action": action}) + "\n" for action in actions
    ))


def test_interactive_full_quest_matches_batch_replay():
    actions = demo_actions()
    output = io.StringIO()
    saved = play_factions(
        original_factions(), input_stream=_stream(actions),
        output_stream=output, checkpoint_every=3,
    )
    assert saved == simulate_factions(original_factions(), actions)
    frames = [json.loads(line) for line in output.getvalue().splitlines()]
    assert frames[-1]["kind"] == "checkpoint"
    assert frames[-1]["checkpoint"] == saved
    assert sum(f["kind"] == "transition" for f in frames) == len(actions)
    assert any(f["kind"] == "transition" and "checkpoint" in f for f in frames)
    assert verify_factions(saved) == saved


def test_checkpoint_resume_and_portable_export():
    actions = demo_actions()
    out = io.StringIO()
    partial = play_factions(
        original_factions(), input_stream=_stream(actions[:4]),
        output_stream=out,
    )
    assert partial["state"]["phase"] == "active"
    checkpoint = json.loads(out.getvalue().splitlines()[-1])["checkpoint"]
    assert checkpoint == partial
    remaining = play_factions(
        session=json.loads(json.dumps(checkpoint)),
        input_stream=_stream(actions[4:]), output_stream=io.StringIO(),
    )
    assert remaining == simulate_factions(original_factions(), actions)
    assert import_factions(export_factions(remaining)) == remaining


def test_unearned_faction_finish_is_not_offered():
    source = original_factions()
    source["ending_requirements"][0]["minimum_standing"][0]["minimum"] = 5
    checkpoint = simulate_factions(source, demo_actions()[:-1])
    actions = legal_faction_actions(checkpoint)
    assert {"kind": "finish", "ending_id": "beacon_lit"} not in actions


def test_bad_input_cannot_mutate_checkpoint_and_quit_is_safe():
    saved = simulate_factions(original_factions(), demo_actions()[:2])
    frozen = copy.deepcopy(saved)
    reader = io.StringIO(
        '{"action":{"kind":"travel","to":"outside"}}\n'
        '{"command":"save"}\n{"command":"quit"}\n'
    )
    output = io.StringIO()
    result = play_factions(session=saved, input_stream=reader, output_stream=output)
    assert result == frozen
    assert saved == frozen
    frames = [json.loads(line) for line in output.getvalue().splitlines()]
    assert any(f["kind"] == "rejected" for f in frames)
    assert frames[-1]["checkpoint"] == saved


def test_rejected_input_budget_and_trusted_digest():
    with pytest.raises(CombatSessionError, match="rejected input budget"):
        play_factions(
            original_factions(), input_stream=io.StringIO("oops\n" * 8),
            output_stream=io.StringIO(),
        )
    with pytest.raises(CombatSessionError, match="trusted source digest"):
        play_factions(
            original_factions(), expected_source_digest="0" * 64,
            input_stream=io.StringIO(), output_stream=io.StringIO(),
        )
    with pytest.raises(CombatSessionError, match="checkpoint interval"):
        play_factions(original_factions(), checkpoint_every=0)


def test_cli_main_dispatch_respects_eof_checkpoint(monkeypatch, capsys):
    from skeleton.__main__ import main
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    assert main(["quest-factions-play", "--demo"]) == 0
    frames = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert frames[0]["kind"] == "prompt"
    assert frames[-1]["kind"] == "checkpoint"
    assert frames[-1]["checkpoint"]["state"]["tick"] == 0
    assert cli(["--demo", "--source-digest", "bad"]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False

"""Interactive NPC play: real commands, recovery and verified checkpoint."""
import io
import json
import sys

import pytest

from skeleton.game.gameplay.scene_npc_encounter import (
    _step, new_encounter, original_encounter, verify_encounter,
)
from skeleton.game.gameplay.scene_npc_interactive import (
    cli, parse_player_action, play_encounter,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError

DEMO_INPUT = "talk quay_keeper assist\ncollect find_key\ntravel north\ntravel inside\nfinish rescued\n"


def _events(output):
    return [json.loads(line) for line in output.getvalue().splitlines()]


def test_player_completes_original_npc_scene_and_gets_replayable_checkpoint():
    output = io.StringIO()
    session = play_encounter(
        original_encounter(), input_stream=io.StringIO(DEMO_INPUT),
        output_stream=output, checkpoint_every=2,
    )
    assert session["state"]["phase"] == "finished"
    assert session["state"]["ending"] == "rescued"
    events = _events(output)
    assert events[0]["event"] == "started"
    assert events[-1]["event"] == "terminal"
    terminal_prompt = [e for e in events if e["event"] == "prompt"][-1]
    assert {"kind": "finish", "ending_id": "rescued"} in terminal_prompt["available_actions"]
    assert all(a["ending_id"] != "lost" for a in terminal_prompt["available_actions"])
    assert any(e["event"] == "checkpoint" and e["reason"] == "interval"
               for e in events)
    assert verify_encounter(
        [e for e in events if e["event"] == "checkpoint"][-1]["session"]
    ) == session


def test_resume_requires_matching_source_digest_and_retains_state():
    source = original_encounter()
    first = _step(new_encounter(source), {
        "kind": "talk", "npc_id": "quay_keeper", "offer_id": "assist",
    })
    output = io.StringIO()
    resumed = play_encounter(
        session=first, expected_source_digest=first["source_digest"],
        input_stream=io.StringIO(
            "collect find_key\ntravel north\ntravel inside\nfinish rescued\n"
        ), output_stream=output,
    )
    assert resumed["state"]["ending"] == "rescued"
    with pytest.raises(SceneTravelError, match="trusted digest"):
        play_encounter(
            session=first, expected_source_digest="0" * 64,
            input_stream=io.StringIO(""), output_stream=io.StringIO(),
        )


def test_eof_emits_last_verified_checkpoint_without_mutating_state():
    output = io.StringIO()
    with pytest.raises(SceneTravelError, match="checkpoint emitted"):
        play_encounter(
            original_encounter(), input_stream=io.StringIO(""),
            output_stream=output,
        )
    checkpoint = _events(output)[-1]
    assert checkpoint["reason"] == "input_eof"
    assert verify_encounter(checkpoint["session"]) == new_encounter(
        original_encounter()
    )


def test_invalid_commands_are_bounded_and_preserve_checkpoint():
    output = io.StringIO()
    with pytest.raises(SceneTravelError, match="retries exhausted"):
        play_encounter(
            original_encounter(),
            input_stream=io.StringIO("teleport nowhere\nbad\nwrong\n"),
            output_stream=output,
        )
    events = _events(output)
    assert len([e for e in events if e["event"] == "invalid"]) == 3
    assert events[-1]["reason"] == "invalid_input_limit"
    assert verify_encounter(events[-1]["session"]) == new_encounter(
        original_encounter()
    )


@pytest.mark.parametrize("text", [
    "", "teleport quay", "talk only", "collect", "finish",
    '{"kind":"talk","kind":"scene"}', "x" * (128 * 1024 + 1),
])
def test_invalid_player_input_is_rejected(text):
    with pytest.raises(SceneTravelError):
        parse_player_action(text)


def test_cli_dispatch_is_real_and_accepts_interactive_input(monkeypatch, capsys):
    from skeleton.__main__ import main
    monkeypatch.setattr(sys, "stdin", io.StringIO(DEMO_INPUT))
    assert main(["scene-npc-play", "--demo"]) == 0
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert events[-1]["ending"] == "rescued"
    assert cli(["--demo", "--source-digest", "0" * 64]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False

"""Interactive turn input, source pinning and EOF checkpoint safety."""
from __future__ import annotations

import io
import json

import pytest

from skeleton.game.gameplay.scene_market_party import (
    new_party, original_party, simulate_party,
)
from skeleton.game.gameplay.scene_market_party_interactive import play_party
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_interactive_complete_and_restartable():
    source, turns = original_party()
    text = "\n".join(json.dumps(turn["action"]) for turn in turns) + "\n"
    output = io.StringIO()
    result = play_party(source, input_stream=io.StringIO(text),
                        output_stream=output, checkpoint_every=3)
    assert result == simulate_party(source, turns)
    events = [json.loads(line) for line in output.getvalue().splitlines()]
    assert events[-1]["event"] == "terminal"
    assert any(e["event"] == "checkpoint" and e["reason"] == "interval"
               for e in events)
    assert events[-2]["session"] == result


def test_eof_emits_replayable_checkpoint():
    source, _ = original_party()
    output = io.StringIO()
    with pytest.raises(SceneTravelError, match="checkpoint emitted"):
        play_party(source, input_stream=io.StringIO(""), output_stream=output)
    events = [json.loads(line) for line in output.getvalue().splitlines()]
    assert events[-1]["reason"] == "input_eof"
    assert events[-1]["session"] == new_party(source)


def test_three_invalid_commands_emit_checkpoint():
    source, _ = original_party()
    output = io.StringIO()
    with pytest.raises(SceneTravelError, match="checkpoint emitted"):
        play_party(source, input_stream=io.StringIO("{}\n{}\n{}\n"),
                   output_stream=output)
    events = [json.loads(line) for line in output.getvalue().splitlines()]
    assert events[-1]["reason"] == "invalid_commands"
    assert events[-1]["session"] == new_party(source)


def test_source_pin_and_checkpoint_bounds():
    source, _ = original_party()
    with pytest.raises(SceneTravelError, match="source digest"):
        play_party(source, expected_source_digest="0" * 64,
                   input_stream=io.StringIO(""))
    with pytest.raises(SceneTravelError, match="checkpoint interval"):
        play_party(source, checkpoint_every=0)

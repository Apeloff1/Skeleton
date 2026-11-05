"""Real terminal gameplay, safe parsing, replayed completion and attempt bounds."""
from __future__ import annotations

from io import StringIO
import json

import pytest

from skeleton.game.gameplay.harbor_crafting import HarborError
from skeleton.game.gameplay.harbor_crafting_patrol import verify_patrol
from skeleton.game.gameplay.harbor_crafting_patrol_ui import (
    parse_command, play_live, render_patrol,
)
from skeleton.testing.test_harbor_crafting_patrol import inputs, actions


def command(action):
    if action["op"] == "move":
        return action["direction"]
    if action["op"] in {"craft", "trade"}:
        return action["op"] + " " + action.get("recipe", action.get("item"))
    if action["op"] == "collect":
        return "collect " + action["objective"]
    return action["op"]


def test_interactive_full_original_game_and_portable_report():
    source, board = inputs()
    commands = "\n".join(command(action) for action in actions()) + "\n"
    output = StringIO()
    report = play_live(source, board, input_stream=StringIO(commands),
                       output_stream=output, require_complete=True)
    assert verify_patrol(report, require_complete=True)["score"] == 18
    assert "FINAL_JSON " in output.getvalue()
    assert json.loads(output.getvalue().split("FINAL_JSON ", 1)[1]) == report
    assert "@" in render_patrol(report)


def test_invalid_command_does_not_mutate_state():
    source, board = inputs()
    output = StringIO()
    report = play_live(source, board, input_stream=StringIO("sudo cheat\nquit\n"),
                       output_stream=output)
    assert report["actions"] == []
    assert "rejected: unsupported patrol command" in output.getvalue()


@pytest.mark.parametrize("line", [
    "", "move diagonal", "collect", "craft", "teleport 4 5",
    "extract now", "north extra", "a" * 193,
])
def test_hostile_terminal_command_rejected(line):
    with pytest.raises(HarborError):
        parse_command(line)


def test_interactive_partial_requires_explicit_completion():
    source, board = inputs()
    with pytest.raises(HarborError, match="not completed"):
        play_live(source, board, input_stream=StringIO("quit\n"),
                  output_stream=StringIO(), require_complete=True)


def test_interactive_invalid_input_is_bounded():
    source, board = inputs()
    board["max_turns"] = 1
    with pytest.raises(HarborError, match="attempt budget"):
        play_live(source, board, input_stream=StringIO("cheat\n" * 5),
                  output_stream=StringIO())

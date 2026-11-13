"""Actual human-readable terminal gameplay and EOF checkpoint acceptance."""
from __future__ import annotations

from io import StringIO
from pathlib import Path
import subprocess
import sys

import pytest

from skeleton.game.gameplay.harbor_crafting import HarborError, decode, load_source, verify_bundle
from skeleton.game.gameplay.harbor_crafting_ui import (
    parse_command, play_live, render, scripted_demo_commands,
)

WORLD = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures" / "harbor_lantern_quay.json"


def world():
    return load_source(WORLD)


def checkpoint_from_output(output: str):
    line = next(line for line in output.splitlines() if line.startswith("CHECKPOINT "))
    return decode(line.removeprefix("CHECKPOINT ").encode("utf-8"))


def test_human_commands_execute_real_game_and_emit_replay_proven_victory():
    output = StringIO()
    code = play_live(world(), StringIO(scripted_demo_commands()), output)
    assert code == 0
    text = output.getvalue()
    assert "LANTERN QUAY" in text
    assert "VICTORY beacon" in text
    assert "delivered=true" in text
    assert "ending=beacon" in text
    bundle = checkpoint_from_output(text)
    assert verify_bundle(bundle, require_win=True)["ending"] == "beacon"


def test_human_gameplay_rendering_is_deterministic():
    a, b = StringIO(), StringIO()
    assert play_live(world(), StringIO(scripted_demo_commands()), a) == 0
    assert play_live(world(), StringIO(scripted_demo_commands()), b) == 0
    assert a.getvalue() == b.getvalue()


def test_terminal_eof_is_not_fake_victory_and_preserves_checkpoint():
    output = StringIO()
    code = play_live(world(), StringIO("east\ngather\n"), output)
    assert code == 2
    assert "VICTORY" not in output.getvalue()
    bundle = checkpoint_from_output(output.getvalue())
    state = verify_bundle(bundle)
    assert state["ending"] is None
    assert state["inventory"]["wood"] == 1


def test_terminal_invalid_move_does_not_mutate_game_state():
    output = StringIO()
    code = play_live(world(), StringIO("north\nsave\nquit\n"), output)
    assert code == 2
    assert "REJECTED movement collision" in output.getvalue()
    bundle = checkpoint_from_output(output.getvalue())
    assert bundle["state"]["tick"] == 0
    assert bundle["state"]["pos"] == [1, 1]


@pytest.mark.parametrize("command", [
    "", "craft", "trade", "craft; rm -rf /", "execute code", "north extra",
    "x" * 129,
])
def test_terminal_command_parser_rejects_untrusted_or_oversized_text(command):
    with pytest.raises(HarborError):
        parse_command(command)


def test_terminal_parser_supports_safe_commands_only():
    assert parse_command("NORTH") == {"op": "move", "direction": "north"}
    assert parse_command("craft lantern") == {"op": "craft", "recipe": "lantern"}
    assert parse_command("trade food") == {"op": "trade", "item": "food"}
    assert parse_command("save") == "save"
    assert parse_command("quit") == "quit"


def test_cli_terminal_play_wins_on_scripted_human_input():
    command = [sys.executable, "-m", "scripts.game.harbor_crafting", "play-live"]
    result = subprocess.run(
        command, input=scripted_demo_commands().encode("utf-8"),
        capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr.decode()
    assert "VICTORY beacon" in result.stdout.decode()
    assert verify_bundle(checkpoint_from_output(result.stdout.decode()), require_win=True)["ending"] == "beacon"


def test_cli_terminal_play_eof_returns_nonzero_and_recoverable_save():
    command = [sys.executable, "-m", "scripts.game.harbor_crafting", "play-live"]
    result = subprocess.run(command, input=b"east\n", capture_output=True, check=False)
    assert result.returncode == 2
    assert "VICTORY" not in result.stdout.decode()
    assert verify_bundle(checkpoint_from_output(result.stdout.decode()))["tick"] == 1

"""Interactive undo/redo must preserve canonical gameplay and earned choices."""
from __future__ import annotations

from io import StringIO
from pathlib import Path

from skeleton.game.gameplay.harbor_crafting import (
    decode, demo_actions, export_bundle, load_source, verify_bundle,
)
from skeleton.game.gameplay.harbor_crafting_ui import (
    parse_command, play_live, scripted_demo_commands,
)

WORLD = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures" / "harbor_lantern_quay.json"


def source():
    return load_source(WORLD)


def play(commands: str):
    output = StringIO()
    code = play_live(source(), StringIO(commands), output)
    return code, output.getvalue()


def last_checkpoint(output: str):
    lines = [line for line in output.splitlines() if line.startswith("CHECKPOINT ")]
    assert lines
    return decode(lines[-1][len("CHECKPOINT "):].encode("utf-8"))


def test_undo_redo_restores_identical_save_and_digests():
    code, output = play("east\nundo\nredo\nsave\nquit\n")
    assert code == 2
    assert "UNDO " in output
    assert "REDO " in output
    restored = last_checkpoint(output)
    assert restored == export_bundle(source(), [{"op": "move", "direction": "east"}])
    assert verify_bundle(restored)["tick"] == 1


def test_undo_branch_invalidates_redo_and_keeps_new_path():
    code, output = play("east\nundo\nsouth\nredo\nquit\n")
    assert code == 2
    assert "REJECTED no action to redo" in output
    restored = last_checkpoint(output)
    assert restored == export_bundle(source(), [{"op": "move", "direction": "south"}])


def test_empty_undo_redo_fail_closed_without_mutating_save():
    code, output = play("undo\nredo\nquit\n")
    assert code == 2
    assert "REJECTED no action to undo" in output
    assert "REJECTED no action to redo" in output
    assert last_checkpoint(output) == export_bundle(source(), [])


def test_repeated_undo_replays_complete_prefix():
    code, output = play("east\neast\nundo\nundo\nredo\nquit\n")
    assert code == 2
    assert last_checkpoint(output) == export_bundle(
        source(), [{"op": "move", "direction": "east"}],
    )


def test_undo_does_not_forge_earned_victory():
    commands = scripted_demo_commands()
    prefix = commands.rsplit("\n", 2)[0] + "\n"
    code, output = play(prefix + "undo\nredo\nsignal\n")
    assert code == 0
    assert "VICTORY beacon " in output
    assert verify_bundle(last_checkpoint(output), require_win=True)["ending"] == "beacon"


def test_terminal_commands_are_bounded_and_exact():
    assert parse_command("undo") == "undo"
    assert parse_command("redo") == "redo"
    for value in ("undo now", "redo 3", "undo!" ):
        try:
            parse_command(value)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid undo command was accepted")

"""Interactive original game acceptance, fog visibility, resume and invalid commands."""
from __future__ import annotations

from io import StringIO
from pathlib import Path
import subprocess
import sys

import pytest

from skeleton.game.gameplay.harbor_crafting import HarborError, canonical, decode, load_source
from skeleton.game.gameplay.harbor_crafting_expedition import verify_expedition
from skeleton.game.gameplay.harbor_crafting_expedition_ui import (
    parse_command, play_expedition_live, render_map, scripted_expedition_commands,
)

FIXTURES = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures"
CLI = [sys.executable, "-m", "skeleton.game.gameplay.harbor_crafting_cli"]


def sources():
    world = load_source(FIXTURES / "harbor_lantern_quay.json")
    def board(name):
        return decode((FIXTURES / ("harbor_lantern_quay_" + name + ".json")).read_bytes())
    return world, board("survey"), board("weather"), board("dialogue")


def test_terminal_plays_real_original_victory_with_verified_save():
    output = StringIO()
    assert play_expedition_live(*sources(), StringIO(
        "map\nstatus\n" + scripted_expedition_commands()), output) == 0
    lines = output.getvalue().splitlines()
    assert any(line.startswith("EXPEDITION_WIN beacon") for line in lines)
    assert sum(line.startswith("ACCEPTED ") for line in lines) == 20
    saved = next(line for line in lines if line.startswith("EXPEDITION_SAVE "))
    report = decode(saved[len("EXPEDITION_SAVE "):].encode())
    assert verify_expedition(report, require_complete=True)["complete"]
    assert report["dialogue"]["flags"] == ["dock_pass"]


def test_fog_map_does_not_reveal_unseen_tiles():
    from skeleton.game.gameplay.harbor_crafting_expedition import build_expedition
    world, survey, weather, dialogue = sources()
    report = build_expedition(world, survey, weather, dialogue, [])
    map_text = render_map(report)
    assert "@" in map_text and "?" in map_text
    assert "N" not in map_text  # merchant is outside initial reveal radius
    assert map_text.count("@") == 1


def test_terminal_rejected_actions_do_not_mutate_save():
    world, survey, weather, dialogue = sources()
    output = StringIO()
    commands = "talk merchant_intro permit\nnorth\nunknown\nquit\n"
    assert play_expedition_live(world, survey, weather, dialogue,
                                StringIO(commands), output) == 0
    text = output.getvalue()
    assert "REJECTED merchant dialogue out of reach" in text
    assert "REJECTED movement collision" in text
    saved = next(line for line in text.splitlines() if line.startswith("EXPEDITION_CHECKPOINT "))
    report = decode(saved[len("EXPEDITION_CHECKPOINT "):].encode())
    assert verify_expedition(report)["complete"] is False
    assert report["input_actions"] == []


def test_terminal_checkpoint_resume_and_stale_lease():
    world, survey, weather, dialogue = sources()
    commands = scripted_expedition_commands().splitlines()
    output = StringIO()
    assert play_expedition_live(world, survey, weather, dialogue,
                                StringIO("\n".join(commands[:17]) + "\nquit\n"),
                                output) == 0
    saved = next(line for line in output.getvalue().splitlines()
                 if line.startswith("EXPEDITION_CHECKPOINT "))
    root = decode(saved[len("EXPEDITION_CHECKPOINT "):].encode())
    output2 = StringIO()
    assert play_expedition_live(world, survey, weather, dialogue,
                                StringIO("\n".join(commands[17:]) + "\n"), output2,
                                root=root, expected_digest=root["expedition_digest"]) == 0
    assert "EXPEDITION_WIN beacon" in output2.getvalue()
    with pytest.raises(HarborError, match="stale"):
        play_expedition_live(world, survey, weather, dialogue, StringIO("quit\n"),
                             StringIO(), root=root, expected_digest="0"*64)


def test_parser_is_bounded_and_strict():
    assert parse_command("talk merchant_intro permit") == {
        "op": "talk", "node": "merchant_intro", "choice": "permit",
    }
    assert parse_command("east") == {"op": "move", "direction": "east"}
    for command in ("", "north extra", "talk merchant_intro", "choose fake extra",
                    "x" * 257):
        with pytest.raises(HarborError):
            parse_command(command)


def test_cli_terminal_full_game_and_stale_checkpoint(tmp_path):
    world, survey, weather, dialogue = sources()
    paths = []
    for name, board in (("survey", survey), ("weather", weather), ("dialogue", dialogue)):
        path = tmp_path / (name + ".json")
        path.write_bytes(canonical(board))
        paths.extend(["--" + name + "-board", str(path)])
    success = subprocess.run(
        CLI + ["expedition-live"] + paths,
        input=scripted_expedition_commands().encode(),
        capture_output=True, check=False,
    )
    assert success.returncode == 0, success.stderr.decode()
    assert b"EXPEDITION_WIN beacon" in success.stdout
    denied = subprocess.run(
        CLI + ["expedition-live"] + paths + [
            "--expected-expedition-digest", "0"*64,
        ], input=b"quit\n", capture_output=True, check=False,
    )
    assert denied.returncode == 2 and denied.stdout == b""

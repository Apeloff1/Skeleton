"""``python -m skeleton game`` CLI adapter."""
from __future__ import annotations

import json

import pytest

from skeleton.forge.game_builder import cli


def test_cli_json(capsys):
    assert cli(["a", "small", "platformer", "--playtest", "off", "--json"]) == 0
    body = json.loads(capsys.readouterr().out)
    assert body["ok"] is True
    assert body["spec"]["genre"] == "platformer"
    assert "_operator" not in body


def test_cli_text(capsys):
    assert cli(["a", "dungeon", "rpg", "--playtest", "off"]) == 0
    out = capsys.readouterr().out
    assert "ok=True" in out and "genre=rpg_roguelike" in out


@pytest.mark.parametrize(
    "argv",
    [[], ["--playtest", "off"], ["x", "--out"], ["x", "--playtest"], ["x", "--max-rounds", "9"],
     ["x", "--max-rounds", "0"], ["x", "--max-rounds"], ["x", "--bogus"]],
)
def test_cli_usage_errors(argv, capsys):
    assert cli(argv) == 2
    assert capsys.readouterr().err.startswith("game:")


def test_cli_writes_project(tmp_path, capsys):
    out = tmp_path / "proj"
    assert cli(["a", "platformer", "--playtest", "off", "--out", str(out)]) == 0
    assert (out / "project.godot").is_file()
    assert "wrote" in capsys.readouterr().out

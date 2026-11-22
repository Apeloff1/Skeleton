"""User-reachable editor parser, scripted commands and create-only output."""
import json
import pytest

from skeleton.game.gameplay.ridge_rescue.workbench_cli import main, parse_command


def test_editor_parser():
    assert parse_command("tile 1 2 #") == {"kind": "set-tile", "target": [1, 2], "value": "#"}
    assert parse_command('name "New Cinder Ridge"') == {
        "kind": "rename", "target": "world", "value": "New Cinder Ridge"}
    assert parse_command("move civilian tavi 2 1")["kind"] == "move-civilian"
    with pytest.raises(ValueError):
        parse_command("rm -rf /")


def test_cli_open_and_verify(capsys):
    assert main(["open"]) == 0
    session = json.loads(capsys.readouterr().out)
    assert session["schema"] == "ridge.rescue.workbench.v1"
    assert main(["inspect"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["valid"] is True


def test_cli_export_create_only(tmp_path):
    output = tmp_path / "editor.json"
    assert main(["export", "--output", str(output)]) == 0
    assert output.exists()
    with pytest.raises(SystemExit) as exc:
        main(["export", "--output", str(output)])
    assert exc.value.code == 2

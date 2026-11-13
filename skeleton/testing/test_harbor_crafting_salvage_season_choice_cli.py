"""Public choice CLI end-to-end package and adversarial rejection."""
from __future__ import annotations

import json

from skeleton.game.gameplay.harbor_crafting_salvage_season_choice_cli import main
from skeleton.testing.test_harbor_crafting_salvage_season import completed_season


def _run(capsys, *argv):
    code = main(list(argv))
    output = capsys.readouterr()
    assert code == 0, output.err
    return json.loads(output.out)


def test_cli_earned_choice_and_package(tmp_path, capsys):
    _, _, full = completed_season()
    save_path = tmp_path / "save.json"
    save_path.write_text(json.dumps(full))
    report = _run(capsys, "choose", "--save", str(save_path), "--choice", "rebuild_quay")
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report))
    assert _run(capsys, "verify", "--report", str(report_path))["remaining_points"] == 16
    options = _run(capsys, "compare", "--save", str(save_path))
    assert len(options["available"]) == 2
    package = _run(capsys, "package", "--save", str(save_path))
    package_path = tmp_path / "package.json"
    package_path.write_text(json.dumps(package))
    play = _run(capsys, "play", "--package", str(package_path),
                "--choice", "merchant_charter")
    play_path = tmp_path / "play.json"
    play_path.write_text(json.dumps(play))
    assert _run(capsys, "verify-play", "--play", str(play_path))["epilogue"] == "open_sea_trade"


def test_cli_refuses_unearned_epilogue(tmp_path, capsys):
    _, _, full = completed_season()
    save_path = tmp_path / "save.json"
    save_path.write_text(json.dumps(full))
    code = main(["choose", "--save", str(save_path), "--choice", "reserve_fleet"])
    assert code == 2
    assert "not earned" in capsys.readouterr().err

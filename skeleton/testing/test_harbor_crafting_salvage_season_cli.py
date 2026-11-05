"""End-user salvage season CLI: full source-to-save-to-package acceptance."""
from __future__ import annotations

import json

from skeleton.game.gameplay.harbor_crafting_salvage_season_cli import main
from skeleton.testing.test_harbor_crafting_salvage import actions
from skeleton.testing.test_harbor_crafting_salvage_season import second_round


def _run(capsys, *args):
    code = main(list(args))
    captured = capsys.readouterr()
    assert code == 0, captured.err
    return json.loads(captured.out)


def test_cli_championship_play_export_verify(tmp_path, capsys):
    rounds = tmp_path / "rounds.json"
    rounds.write_text(json.dumps([actions(), second_round()]))
    package = _run(capsys, "package")
    package_path = tmp_path / "package.json"
    package_path.write_text(json.dumps(package))
    play = _run(capsys, "play", "--package", str(package_path),
                "--rounds", str(rounds), "--require-complete")
    play_path = tmp_path / "play.json"
    play_path.write_text(json.dumps(play))
    assert _run(capsys, "verify-play", "--play", str(play_path),
                "--require-complete")["score"] == 36
    acceptance = _run(capsys, "accept", "--rounds", str(rounds))
    accepted_path = tmp_path / "acceptance.json"
    accepted_path.write_text(json.dumps(acceptance))
    assert _run(capsys, "verify-accept", "--acceptance", str(accepted_path))["complete"]


def test_cli_cas_round_resume_and_history(tmp_path, capsys):
    start = _run(capsys, "start")
    save_path = tmp_path / "save.json"
    save_path.write_text(json.dumps(start))
    round_path = tmp_path / "round.json"
    round_path.write_text(json.dumps(actions()))
    first = _run(capsys, "next", "--save", str(save_path),
                 "--actions", str(round_path), "--expected-tip", start["tip"])
    save_path.write_text(json.dumps(first))
    assert _run(capsys, "verify", "--save", str(save_path))["rounds_earned"] == 1
    at = _run(capsys, "at", "--save", str(save_path), "--index", "0")
    assert at["reports"] == []

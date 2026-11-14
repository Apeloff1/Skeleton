"""Player-reachable league CLI and safe create-only publication."""
import json
import pytest
from skeleton.game.gameplay.ridge_rescue.league_cli import main


def test_cli_open_and_rank(capsys):
    assert main(["open"]) == 0
    board = json.loads(capsys.readouterr().out)
    assert board["schema"] == "ridge.rescue.league.board.v1"
    assert main(["rank"]) == 0
    ranking = json.loads(capsys.readouterr().out)
    assert ranking["valid"] and ranking["entries"] == 0


def test_cli_rejects_missing_submission_and_overwrite(tmp_path):
    with pytest.raises(SystemExit) as exc:
        main(["submit"])
    assert exc.value.code == 2
    output = tmp_path / "league.json"
    assert main(["open", "--output", str(output)]) == 0
    with pytest.raises(SystemExit) as exc:
        main(["open", "--output", str(output)])
    assert exc.value.code == 2

"""User-reachable CLI tactics checks with safe no-overwrite export."""
import json
import pytest
from skeleton.game.gameplay.ridge_rescue.tactics_cli import main


def test_cli_open_suggest_and_bounded_autoplay(capsys):
    assert main(["open"]) == 0
    journal = json.loads(capsys.readouterr().out)
    assert journal["schema"] == "ridge.rescue.journal.v1"
    assert main(["suggest"]) == 0
    advice = json.loads(capsys.readouterr().out)
    assert advice["ranked"] and advice["guaranteed"] is False
    assert main(["autoplay"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["steps_executed"] <= 72
    assert result["guaranteed"] is False


def test_cli_create_only_and_stale_revision(tmp_path):
    output = tmp_path / "tactics.json"
    assert main(["inspect", "--output", str(output)]) == 0
    assert output.exists()
    with pytest.raises(SystemExit) as exc:
        main(["inspect", "--output", str(output)])
    assert exc.value.code == 2
    with pytest.raises(SystemExit) as exc:
        main(["step", "--expected-head", "0" * 64])
    assert exc.value.code == 2

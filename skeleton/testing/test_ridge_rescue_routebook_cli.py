"""Player-reachable CLI routebook acceptance and safe create-only output."""
import json
from pathlib import Path

import pytest

from skeleton.game.gameplay.ridge_rescue.routebook_cli import main
from skeleton.game.gameplay.ridge_rescue.routebook import verify_route_export


def test_inspect_and_play_both_earned_endings(capsys):
    assert main(["inspect"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert len(report["tracks"]) == 2
    for track, ending in (("protect-route", "protect"), ("salvage-route", "salvage")):
        assert main(["run", "--track", track]) == 0
        bundle = json.loads(capsys.readouterr().out)
        assert verify_route_export(bundle)["state"]["status"] == "won:" + ending


def test_cli_export_file_create_only(tmp_path):
    output = tmp_path / "route.json"
    assert main(["run", "--output", str(output)]) == 0
    assert verify_route_export(output.read_bytes())["status"] == "completed"
    with pytest.raises(SystemExit) as exc:
        main(["run", "--output", str(output)])
    assert exc.value.code == 2


def test_cli_missing_required_session_fails_closed():
    with pytest.raises(SystemExit) as exc:
        main(["step"])
    assert exc.value.code == 2

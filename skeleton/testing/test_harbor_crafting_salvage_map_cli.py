"""User-facing original ASCII scene export and independent replay verification."""
from __future__ import annotations

import json

from skeleton.game.gameplay.harbor_crafting_salvage_map_cli import main
from skeleton.game.gameplay.harbor_crafting_salvage import build_salvage
from skeleton.testing.test_harbor_crafting_salvage import inputs, actions


def test_map_cli_export_verify_and_print(tmp_path, capsys):
    source, board = inputs()
    report = build_salvage(source, board, actions(), require_complete=True)
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report))
    assert main(["render", "--report", str(report_path), "--reveal"]) == 0
    view = json.loads(capsys.readouterr().out)
    view_path = tmp_path / "view.json"
    view_path.write_text(json.dumps(view))
    assert main(["verify", "--view", str(view_path)]) == 0
    assert json.loads(capsys.readouterr().out) == view["frame"]
    assert main(["print", "--view", str(view_path)]) == 0
    assert "@" in capsys.readouterr().out

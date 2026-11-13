"""Portable patrol, transactional editing, CLI and adversarial replay."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from skeleton.game.gameplay.harbor_crafting import HarborError, digest
from skeleton.game.gameplay.harbor_crafting_patrol import build_patrol
from skeleton.game.gameplay.harbor_crafting_patrol_authoring import (
    edit_patrol_board, verify_patrol_revision,
)
from skeleton.game.gameplay.harbor_crafting_patrol_package import (
    build_patrol_package, play_patrol_package, verify_patrol_package,
    verify_patrol_package_play,
)
from skeleton.game.gameplay.harbor_crafting_patrol_cli import main
from skeleton.testing.test_harbor_crafting_patrol import inputs, actions


def test_transactional_edit_replay_and_preview():
    source, board = inputs()
    edits = [{"op": "set-objective-reward", "id": "tide_registry", "value": 20},
             {"op": "set-guard-sight", "id": "breakwater_watch", "value": 0}]
    revision = edit_patrol_board(source, board, edits,
                                 expected_digest=digest(board), preview_actions=actions())
    assert verify_patrol_revision(revision)["objectives"][0]["reward"] == 20
    assert revision["preview_before"]["state"]["score"] == 18
    assert revision["preview_after"]["state"]["score"] == 31
    assert board["objectives"][0]["reward"] == 7
    with pytest.raises(HarborError, match="stale"):
        edit_patrol_board(source, board, edits, expected_digest="0" * 64)
    damaged = deepcopy(revision)
    damaged["after"]["alert_limit"] = 1
    damaged["revision_digest"] = digest({k: v for k, v in damaged.items()
                                          if k != "revision_digest"})
    with pytest.raises(HarborError):
        verify_patrol_revision(damaged)


def test_package_demo_and_user_play_are_replayed():
    source, board = inputs()
    package = build_patrol_package(source, board, actions(), package_id="original_patrol")
    assert verify_patrol_package(package)["demo_score"] == 18
    play = play_patrol_package(package, actions(), require_complete=True)
    assert verify_patrol_package_play(play, require_complete=True)["score"] == 18
    assert play == play_patrol_package(package, actions(), require_complete=True)
    with pytest.raises(HarborError):
        build_patrol_package(source, board, actions()[:5], package_id="unearned")
    damaged = deepcopy(play)
    damaged["report"]["state"]["score"] = 999
    damaged["play_digest"] = digest({k: v for k, v in damaged.items()
                                      if k != "play_digest"})
    with pytest.raises(HarborError):
        verify_patrol_package_play(damaged)


def test_cli_full_source_to_package_to_replay(tmp_path, capsys):
    actions_path = tmp_path / "actions.json"
    actions_path.write_text(json.dumps(actions()))
    assert main(["run", "--actions", str(actions_path), "--require-complete"]) == 0
    report = json.loads(capsys.readouterr().out)
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report))
    assert main(["verify", "--report", str(report_path), "--require-complete"]) == 0
    assert json.loads(capsys.readouterr().out)["score"] == 18
    assert main(["package", "--actions", str(actions_path)]) == 0
    package = json.loads(capsys.readouterr().out)
    package_path = tmp_path / "package.json"
    package_path.write_text(json.dumps(package))
    assert main(["play", "--package", str(package_path),
                 "--actions", str(actions_path), "--require-complete"]) == 0
    play = json.loads(capsys.readouterr().out)
    play_path = tmp_path / "play.json"
    play_path.write_text(json.dumps(play))
    assert main(["verify-play", "--play", str(play_path), "--require-complete"]) == 0
    assert json.loads(capsys.readouterr().out)["complete"] is True


def test_cli_rejects_invalid_json_and_stale_revision(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text('{"op":"wait","op":"move"}')
    assert main(["run", "--actions", str(bad)]) == 2
    assert "invalid canonical JSON" in capsys.readouterr().err
    edits = tmp_path / "edits.json"
    edits.write_text('[{"op":"set-alert-limit","value":3}]')
    assert main(["author", "--edits", str(edits),
                 "--expected-digest", "0" * 64]) == 2
    assert "stale" in capsys.readouterr().err

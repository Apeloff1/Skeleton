"""Source-bound patrol endings and independent replay verification."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from skeleton.game.gameplay.harbor_crafting import HarborError, digest
from skeleton.game.gameplay.harbor_crafting_patrol import build_patrol
from skeleton.game.gameplay.harbor_crafting_patrol_debrief import (
    build_patrol_debrief, compare_patrol_debriefs, validate_debrief_board,
    verify_patrol_debrief,
)
from skeleton.game.gameplay.harbor_crafting_patrol_cli import main
from skeleton.testing.test_harbor_crafting_patrol import inputs, actions

FIXTURES = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures"


def inputs_and_report():
    source, board = inputs()
    patrol = build_patrol(source, board, actions(), require_complete=True)
    debrief = json.loads((FIXTURES / "harbor_lantern_quay_patrol_debrief.json").read_text())
    return patrol, debrief


def test_two_distinct_earned_original_epilogues():
    patrol, board = inputs_and_report()
    choices = compare_patrol_debriefs(patrol, board)
    assert choices["available"] == ["publish", "protect"]
    publish = build_patrol_debrief(patrol, board, "publish")
    protect = build_patrol_debrief(patrol, board, "protect")
    assert verify_patrol_debrief(publish)["epilogue"] == "watch_restored"
    assert verify_patrol_debrief(protect)["epilogue"] == "families_sheltered"
    assert publish["outcome"]["remaining_score"] == 14
    assert protect["outcome"]["remaining_score"] == 11
    assert publish["report_digest"] != protect["report_digest"]


def test_unearned_debrief_fails_closed():
    patrol, board = inputs_and_report()
    board["choices"][0]["min_score"] = 100
    assert compare_patrol_debriefs(patrol, board)["available"] == ["protect"]
    with pytest.raises(HarborError, match="not earned"):
        build_patrol_debrief(patrol, board, "publish")
    with pytest.raises(HarborError):
        build_patrol_debrief(patrol, board, "forged")


@pytest.mark.parametrize("mutate", [
    lambda b: b["choices"][0].update(id="protect"),
    lambda b: b["choices"][0].update(cost=11),
    lambda b: b["choices"][0].update(max_alert=True),
    lambda b: b["choices"][1].update(epilogue="../../bad"),
    lambda b: b.update(source_id="other_world"),
    lambda b: b.update(choices=[]),
])
def test_hostile_debrief_board_rejected(mutate):
    patrol, board = inputs_and_report()
    mutate(board)
    with pytest.raises(HarborError):
        validate_debrief_board(board, patrol)


def test_recomputed_digest_cannot_forge_earned_outcome():
    patrol, board = inputs_and_report()
    original = build_patrol_debrief(patrol, board, "protect")
    damaged = deepcopy(original)
    damaged["outcome"]["credits"] = 999
    damaged["report_digest"] = digest({k: v for k, v in damaged.items()
                                        if k != "report_digest"})
    with pytest.raises(HarborError):
        verify_patrol_debrief(damaged)


def test_cli_choices_and_debrief_roundtrip(tmp_path, capsys):
    patrol, board = inputs_and_report()
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(patrol))
    assert main(["choices", "--report", str(report_path)]) == 0
    assert json.loads(capsys.readouterr().out)["available"] == ["publish", "protect"]
    assert main(["debrief", "--report", str(report_path), "--choice", "protect"]) == 0
    debrief = json.loads(capsys.readouterr().out)
    path = tmp_path / "debrief.json"
    path.write_text(json.dumps(debrief))
    assert main(["verify-debrief", "--debrief", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["ending"] == "protect"

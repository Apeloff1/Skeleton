"""Earned branching epilogues, transactional choices and portable replay."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from skeleton.game.gameplay.harbor_crafting import HarborError, digest
from skeleton.game.gameplay.harbor_crafting_salvage_season_choices import (
    build_season_choice, compare_season_choices, verify_season_choice,
)
from skeleton.game.gameplay.harbor_crafting_salvage_season_choice_authoring import (
    edit_season_choices, verify_season_choice_revision,
)
from skeleton.game.gameplay.harbor_crafting_salvage_season_choice_package import (
    build_choice_package, play_choice_package, verify_choice_package_play,
)
from skeleton.testing.test_harbor_crafting_salvage_season import completed_season

FIXTURES = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures"


def choice_board():
    return json.loads((FIXTURES / "harbor_lantern_quay_salvage_season_choices.json").read_text())


def test_earned_endings_and_unearned_fleet_rejected():
    start, first, full = completed_season()
    report = build_season_choice(full, choice_board(), "rebuild_quay")
    assert verify_season_choice(report)["remaining_points"] == 16
    assert verify_season_choice(report)["epilogue"] == "community_beacon"
    options = compare_season_choices(full, choice_board())
    assert len(options["available"]) == 2
    assert options["unavailable"] == ["reserve_fleet"]
    with pytest.raises(HarborError):
        build_season_choice(first, choice_board(), "rebuild_quay")
    with pytest.raises(HarborError, match="not earned"):
        build_season_choice(full, choice_board(), "reserve_fleet")


def test_choice_authoring_preview_and_replay():
    _, _, full = completed_season()
    board = choice_board()
    edits = [{"op": "set-choice", "id": "rebuild_quay",
              "field": "reputation", "value": 18}]
    revision = edit_season_choices(full, board, edits,
                                   expected_board_digest=digest(board),
                                   preview_choice="rebuild_quay")
    assert verify_season_choice_revision(revision)["choices"][0]["reputation"] == 18
    assert revision["preview_after"]["reputation"] == 18
    assert board["choices"][0]["reputation"] == 12


def test_choice_portable_package_and_tamper():
    _, _, full = completed_season()
    package = build_choice_package(full, choice_board(), package_id="earned_epilogues")
    play = play_choice_package(package, "merchant_charter")
    assert verify_choice_package_play(play)["epilogue"] == "open_sea_trade"
    damaged = deepcopy(play)
    damaged["report"]["outcome"]["reputation"] = 100
    damaged["play_digest"] = digest({k: v for k, v in damaged.items()
                                      if k != "play_digest"})
    with pytest.raises(HarborError):
        verify_choice_package_play(damaged)

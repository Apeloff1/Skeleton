"""Playtest quality gate: pure grading plus native Godot runs.

Native cases need Godot 4; set SKELETON_GAME_BUILDER_REQUIRE_GODOT=1 to make
its absence fail instead of skip.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from skeleton.forge.game_builder import build_playable_game
from skeleton.forge.game_design_spec import GOLDEN_BRIEFS
from skeleton.forge.playable_runtime import RUNTIME_PATH
from skeleton.forge.quality_gate import (
    GATE_SCHEMA,
    evaluate_receipt,
    interactive_playtest,
    parse_receipt,
)

BASE = {
    "phase": "won",
    "pause_verified": True,
    "restart_verified": True,
    "save_verified": True,
    "input_frames": 400,
    "movement_distance": 900.0,
    "elapsed": 12.5,
    "hp": 70,
    "score": 900,
}
GOOD = {
    "top_down_shooter": {
        **BASE,
        "genre": "top_down_shooter",
        "shots": 40,
        "defeated": 12,
    },
    "rpg_roguelike": {**BASE, "genre": "rpg_roguelike", "shots": 20, "defeated": 6},
    "platformer": {**BASE, "genre": "platformer", "jumps": 9, "collected": 5},
    "puzzle": {
        **BASE,
        "genre": "puzzle",
        "mistakes": 0,
        "puzzle_solved": True,
        "activations": 12,
    },
}
PUZZLE_CONTENT = {"puzzle": {"moves": 12}}


@pytest.mark.parametrize("genre", sorted(GOOD))
def test_good_receipts_pass(genre):
    graded = evaluate_receipt(GOOD[genre], {"genre": genre}, PUZZLE_CONTENT)
    assert graded == {**graded, "schema": GATE_SCHEMA, "passed": True, "failures": []}


@pytest.mark.parametrize(
    ("genre", "change", "needle"),
    [
        ("top_down_shooter", {"phase": "lost"}, "did not win"),
        ("top_down_shooter", {"save_verified": False}, "save verified"),
        ("top_down_shooter", {"pause_verified": None}, "pause verified"),
        ("top_down_shooter", {"input_frames": 5}, "input frames"),
        ("top_down_shooter", {"movement_distance": 10.0}, "movement"),
        ("top_down_shooter", {"elapsed": 1.0}, "pacing window"),
        ("top_down_shooter", {"elapsed": 300.0}, "pacing window"),
        ("top_down_shooter", {"hp": 0}, "vitality"),
        ("top_down_shooter", {"defeated": 2}, "fewer than 3"),
        ("rpg_roguelike", {"shots": 0}, "never fired"),
        ("platformer", {"jumps": 0}, "never jumped"),
        ("platformer", {"collected": 4}, "every crystal"),
        ("puzzle", {"mistakes": 1}, "mistakes"),
        ("puzzle", {"activations": 11}, "content moves"),
        ("puzzle", {"puzzle_solved": False}, "not solved"),
        ("puzzle", {"genre": "platformer"}, "receipt genre"),
        ("platformer", {"elapsed": float("nan")}, "pacing window"),
        ("platformer", {"input_frames": True}, "input frames"),
    ],
)
def test_each_threshold_fails_closed(genre, change, needle):
    graded = evaluate_receipt(
        {**GOOD[genre], **change}, {"genre": genre}, PUZZLE_CONTENT
    )
    assert graded["passed"] is False
    assert any(needle in failure for failure in graded["failures"]), graded["failures"]


def test_unknown_genre_has_no_free_pass():
    graded = evaluate_receipt({**BASE, "genre": "racing"}, {"genre": "racing"})
    assert (
        graded["passed"] is False and "no quality thresholds" in graded["failures"][-1]
    )


def test_receipt_parsing_requires_exactly_one_json_object():
    assert parse_receipt('noise\nFORGE_INTERACTIVE_OK {"a": 1}\n') == {"a": 1}
    assert parse_receipt("FORGE_INTERACTIVE_OK {}\nFORGE_INTERACTIVE_OK {}") is None
    assert parse_receipt("FORGE_INTERACTIVE_OK [1]") is None
    assert parse_receipt("FORGE_INTERACTIVE_OK {bad") is None
    assert parse_receipt("") is None


def test_projects_without_a_replay_are_not_applicable():
    report = interactive_playtest(
        {"project.godot": "config_version=5\n"}, {"genre": "platformer"}
    )
    assert report["status"] == "not_applicable" and report["passed"] is False


@pytest.fixture(scope="module")
def godot():
    selected = (
        os.environ.get("SKELETON_GODOT_BIN")
        or shutil.which("godot4")
        or shutil.which("godot")
    )
    if not selected or not Path(selected).is_file():
        if os.environ.get("SKELETON_GAME_BUILDER_REQUIRE_GODOT") == "1":
            pytest.fail("quality gate acceptance requires an installed Godot 4 binary")
        pytest.skip(
            "native Godot not installed; the quality gate is not qualified by this skip"
        )
    return selected


@pytest.mark.parametrize(
    "genre", ["top_down_shooter", "platformer", "rpg_roguelike", "puzzle"]
)
def test_required_playtest_runs_the_quality_gate_and_verifies_the_input_journey(
    godot, genre
):
    brief = next(item["brief"] for item in GOLDEN_BRIEFS if item["genre"] == genre)
    result = build_playable_game(brief, playtest_mode="require", binary=godot)
    assert result["ok"] is True, result.get("error")
    gate = result["playtest"]["quality"]
    assert gate["status"] == "passed", gate
    assert gate["receipt"]["genre"] == genre and gate["failures"] == []
    assert result["interactive"]["input_journey_verified"] is True
    assert result["interactive"]["native_boot_verified"] is True


def test_gate_failures_block_the_build(godot):
    brief = next(
        item["brief"] for item in GOLDEN_BRIEFS if item["genre"] == "top_down_shooter"
    )
    result = build_playable_game(brief, playtest_mode="off")
    files = dict(result["files"])
    mismatched = interactive_playtest(files, {"genre": "platformer"}, binary=godot)
    assert mismatched["status"] == "failed" and any(
        "receipt genre" in f for f in mismatched["failures"]
    )
    files[RUNTIME_PATH] = files[RUNTIME_PATH].replace(
        "func _finish(success: bool) -> void:",
        "func _finish(success: bool) -> void:\n    success = false",
        1,
    )
    unwinnable = interactive_playtest(
        files, result["spec"], result["content"], binary=godot
    )
    assert unwinnable["status"] == "failed" and unwinnable["passed"] is False


def test_playtest_off_never_claims_the_input_journey():
    brief = next(item["brief"] for item in GOLDEN_BRIEFS if item["genre"] == "puzzle")
    result = build_playable_game(brief, playtest_mode="off")
    assert result["ok"] is True and result["playtest"] is None
    assert result["interactive"]["input_journey_verified"] is False

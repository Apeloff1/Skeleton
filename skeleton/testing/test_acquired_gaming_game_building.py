"""Contracts for the reusable AI game-building skill."""

from __future__ import annotations

import pytest

from skeleton.acquired.gaming import (
    GAME_BUILDING_SECTION,
    GameBuildingSkill,
    apply_game_building_skill,
    game_building_requirements,
    validate_game_brief,
)


def test_default_requirements_cover_playable_game_contract():
    requirements = game_building_requirements()
    text = " ".join(requirements).lower()

    for concept in (
        "core gameplay loop",
        "controls",
        "restart",
        "win",
        "loss",
        "progression",
        "feedback",
        "softlocks",
        "playtest",
    ):
        assert concept in text


def test_context_and_constraints_are_normalized_and_deduplicated():
    requirements = game_building_requirements(
        genre="  arcade\n racer ",
        runtime=" browser   WebGL ",
        extra_constraints=("60 FPS", " 60   FPS ", "offline capable"),
    )
    contextual = requirements[-4:]

    assert contextual[0] == (
        "Genre context: design for arcade racer while keeping the core loop explicit and testable."
    )
    assert contextual[1] == (
        "Runtime context: target browser WebGL; preserve its API, performance, input, and packaging constraints."
    )
    assert contextual[2:] == (
        "Project constraint: 60 FPS",
        "Project constraint: offline capable",
    )


def test_prompt_application_preserves_request_and_is_idempotent():
    prompt = "Build a checkpoint racer with keyboard controls."
    skill = GameBuildingSkill(genre="arcade racer", runtime="browser")

    enhanced = skill.apply(prompt)
    enhanced_twice = skill.apply(enhanced)

    assert enhanced.startswith(prompt)
    assert enhanced.count(GAME_BUILDING_SECTION) == 1
    assert "Genre context: design for arcade racer" in enhanced
    assert "Runtime context: target browser" in enhanced
    assert enhanced_twice == enhanced


def test_prompt_application_accepts_empty_prompt_and_rejects_non_string():
    assert apply_game_building_skill("").startswith(GAME_BUILDING_SECTION)
    with pytest.raises(TypeError, match="prompt must be a string"):
        apply_game_building_skill(None)  # type: ignore[arg-type]


def test_brief_validation_reports_each_missing_playability_dimension():
    issues = validate_game_brief({"goal": "Reach the finish line"})

    assert [issue.code for issue in issues] == [
        "missing_core_loop",
        "missing_controls",
        "missing_win_conditions",
        "missing_loss_conditions",
        "missing_restart_behavior",
        "missing_feedback",
        "missing_progression",
    ]
    assert all(issue.field and issue.message for issue in issues)


def test_complete_brief_accepts_aliases_and_structured_values():
    brief = {
        "objective": "Clear every checkpoint before time expires.",
        "gameplay_loop": ["steer", "boost", "cross checkpoint", "repeat"],
        "inputs": {"left": "A", "right": "D", "boost": "Space"},
        "success_condition": "Final checkpoint crossed.",
        "failure_condition": "Timer reaches zero.",
        "retry": "Reset car, timer, score, and checkpoint index.",
        "player_feedback": ["HUD timer", "checkpoint flash", "boost audio"],
        "difficulty_curve": "Later checkpoints tighten the time budget.",
    }

    assert validate_game_brief(brief) == ()
    assert GameBuildingSkill().validate(brief) == ()


def test_blank_values_do_not_satisfy_brief_contract():
    issues = validate_game_brief(
        {
            "player_goal": "   ",
            "core_loop": [],
            "controls": {},
        }
    )

    codes = {issue.code for issue in issues}
    assert "missing_player_goal" in codes
    assert "missing_core_loop" in codes
    assert "missing_controls" in codes


def test_brief_must_be_mapping():
    with pytest.raises(TypeError, match="brief must be a mapping"):
        validate_game_brief([])  # type: ignore[arg-type]

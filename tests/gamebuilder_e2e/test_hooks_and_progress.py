"""Planner / QA hooks and progress callbacks."""
from __future__ import annotations

from skeleton.forge.game_builder import build_playable_game

BRIEF = "a small platformer about a fox"


def test_progress_is_monotonic_and_bounded():
    seen: list[tuple[float, str]] = []
    result = build_playable_game(BRIEF, playtest_mode="off", on_progress=lambda f, m: seen.append((f, m)))
    assert result["ok"] is True
    fractions = [f for f, _ in seen]
    assert fractions and fractions == sorted(fractions)
    assert all(0.0 <= f <= 1.0 for f in fractions)
    assert all(isinstance(m, str) and m for _, m in seen)


def test_qa_hook_is_called_with_view():
    calls = []

    def qa(view):
        calls.append(view)
        return {"repair_requested": False}

    result = build_playable_game(BRIEF, playtest_mode="off", qa=qa)
    assert result["ok"] is True
    assert len(calls) == 1
    assert isinstance(calls[0], dict)


def test_planner_cannot_change_locked_fields():
    def planner(spec):
        return {**spec, "genre": "rpg_roguelike", "engine": "unity", "scope": "large"}

    result = build_playable_game(BRIEF, playtest_mode="off", planner=planner)
    assert result["spec"]["genre"] == "platformer"
    assert result["spec"]["engine"] == "godot4"
    assert result["spec"]["scope"] == "small"


def test_raising_planner_does_not_crash_build():
    def planner(spec):
        raise RuntimeError("planner down")

    result = build_playable_game(BRIEF, playtest_mode="off", planner=planner)
    assert result["spec"]["genre"] == "platformer"

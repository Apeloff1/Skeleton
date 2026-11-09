"""Pipeline verifier tests.

Locks the shared quality contract on the pipeline path so game-logic specs,
plan cards, and forge artefacts expose the same acceptance language.
"""
from __future__ import annotations

from skeleton.intelligence.pipeline_verifier import PipelineVerifier


def test_pipeline_verifier_accepts_grounded_game_logic():
    verifier = PipelineVerifier()
    report = verifier.verify_game_logic(
        {
            "title": "Arena Ops",
            "combat": {"base_values": {"health": 100, "attack": 10}, "damage_formula": "atk * 2"},
            "economy": {"currency": "credits", "starting_balance": 50},
            "progression": {"curve": "quadratic", "max_level": 20},
        },
        description="arena credits quadratic combat",
    )
    assert report.accepted
    assert report.reason == "accepted"
    assert report.quality.metadata["kind"] == "pipeline"
    assert report.quality.metadata["pipeline"] == "game_logic"


def test_pipeline_verifier_rejects_broken_game_logic():
    verifier = PipelineVerifier()
    report = verifier.verify_game_logic(
        {
            "title": "Broken Ops",
            "combat": {"base_values": {"health": -1}, "damage_formula": ""},
            "economy": {"currency": "", "starting_balance": -5},
            "progression": {"curve": "", "max_level": 0},
        },
        description="broken stealth sim",
    )
    assert not report.accepted
    assert report.reason == "low_score"
    assert report.summary["hard_issues"] >= 1
    assert any(i.severity == "hard" for i in report.quality.issues)


def test_pipeline_verifier_stats_track_runs():
    verifier = PipelineVerifier()
    verifier.verify_game_logic(
        {
            "title": "Arena Ops",
            "combat": {"base_values": {"health": 100}, "damage_formula": "atk"},
            "economy": {"currency": "gold", "starting_balance": 1},
            "progression": {"curve": "linear", "max_level": 2},
        },
        description="arena gold linear",
    )
    stats = verifier.stats()
    assert stats["runs"] == 1
    assert 0.0 <= stats["accept_rate"] <= 1.0

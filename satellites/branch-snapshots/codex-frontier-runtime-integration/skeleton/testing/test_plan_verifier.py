"""Plan verifier tests.

Locks the shared quality contract on the plan path so build-plan cards and
forge artefacts expose the same acceptance language.
"""
from __future__ import annotations

from skeleton.intelligence.plan_verifier import PlanVerifier


def test_plan_verifier_accepts_complete_grounded_plan():
    verifier = PlanVerifier()
    report = verifier.verify(
        {
            "era": "soulslike",
            "title": "Elden Ring",
            "citation": "Steam",
            "url": "https://store.steampowered.com/app/1245620/ELDEN_RING/",
            "room_bias": "pressure labyrinth",
            "primary_dps": 144.0,
        },
        vision="like Elden Ring pressure labyrinth",
    )
    assert report.accepted
    assert report.reason == "accepted"
    assert report.quality.metadata["kind"] == "plan"
    assert report.quality.weakest_path in {"completeness", "coherence", "grounding", "actionability"}


def test_plan_verifier_rejects_thin_plan():
    verifier = PlanVerifier()
    report = verifier.verify({"era": "", "room_bias": "", "primary_dps": None}, vision="stealth sim")
    assert not report.accepted
    assert report.reason == "low_score"
    assert report.summary["issue_count"] >= 1
    assert any(i.severity in {"hard", "soft"} for i in report.quality.issues)


def test_plan_verifier_stats_track_runs():
    verifier = PlanVerifier()
    verifier.verify({"era": "soulslike", "room_bias": "arena", "primary_dps": 100}, vision="arena")
    stats = verifier.stats()
    assert stats["runs"] == 1
    assert 0.0 <= stats["accept_rate"] <= 1.0

from __future__ import annotations

from skeleton.persistence.spine_cut_gate import SpineCutGate
from skeleton.persistence.spine_surface import SpineSurface


def test_switch_is_refused_even_when_reads_match() -> None:
    card = SpineCutGate().consider(
        {"hit": True, "applied": 0},
        {"match": True},
    )
    assert card["switched"] is False
    assert card["hit"] is False
    assert card["reasons"] == ["switch-not-landed"]
    assert card["applied_fence"] is False
    assert card["completion_checkbox"] is False


def test_mismatch_is_recorded_and_still_not_switched() -> None:
    card = SpineCutGate().consider({"hit": False, "applied": 0}, {"match": False})
    assert card["switched"] is False
    assert "cutover-miss" in card["reasons"]
    assert "chain-mismatch" in card["reasons"]


def test_surface_is_not_claimed_green() -> None:
    card = SpineSurface().card()
    assert card["provider_surface_green"] is False
    assert card["pr_automation_green"] is False
    assert card["live_motor"] is False
    assert card["hit"] is False

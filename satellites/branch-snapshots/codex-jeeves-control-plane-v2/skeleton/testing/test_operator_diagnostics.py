"""Operator diagnostics tests."""
from __future__ import annotations

from skeleton.organism.activity_card import activity_card
from skeleton.organism.failure_card import failure_card
from skeleton.organism.recurring_card import recurring_card
from skeleton.organism.repair_card import repair_card
from skeleton.organism.quality_state import append_quality, append_repair


def test_failure_card_can_filter_surface(tmp_path):
    append_quality({"surface": "forge", "accepted": False, "reason": "unsafe_code", "score": 0.1}, root=tmp_path)
    append_quality({"surface": "npc", "accepted": False, "reason": "low_score", "score": 0.2}, root=tmp_path)
    card = failure_card(root=tmp_path, surface="forge")
    assert card["surface"] == "forge"
    assert card["latest"]["surface"] == "forge"


def test_activity_card_filters_kind(tmp_path):
    append_quality({"surface": "forge", "accepted": False, "reason": "unsafe_code", "score": 0.1}, root=tmp_path)
    append_repair({"surface": "forge", "ok": 1, "before": {"reason": "unsafe_code"}, "after": {"reason": "accepted", "score": 0.8}}, root=tmp_path)
    card = activity_card(root=tmp_path, kind="repair")
    assert card["entry_kind"] == "repair"
    assert card["n"] == 1


def test_recurring_card_filters_surface(tmp_path):
    append_repair({"surface": "plan", "ok": 1, "before": {"reason": "low_score"}, "after": {"reason": "accepted", "score": 0.9}, "targeted_path": "room_bias"}, root=tmp_path)
    append_repair({"surface": "forge", "ok": 1, "before": {"reason": "unsafe_code"}, "after": {"reason": "accepted", "score": 0.8}, "targeted_path": "a.gd"}, root=tmp_path)
    card = recurring_card(root=tmp_path, surface="plan")
    assert card["surface"] == "plan"


def test_repair_card_filters_surface(tmp_path):
    append_quality({"surface": "plan", "accepted": False, "reason": "low_score", "score": 0.2}, root=tmp_path)
    append_repair({"surface": "plan", "ok": 1, "before": {"reason": "low_score"}, "after": {"reason": "accepted", "score": 0.9}}, root=tmp_path)
    card = repair_card(root=tmp_path, surface="plan")
    assert card["surface"] == "plan"

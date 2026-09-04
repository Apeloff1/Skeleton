"""Operator quality surface tests."""
from __future__ import annotations


def test_product_card_exposes_quality(tmp_path):
    from skeleton.organism.product import product_card
    from skeleton.organism.quality_state import append_quality, append_repair
    from skeleton.organism.organismer import Organismer
    from skeleton.galaxy.system import GalaxySystem

    append_quality({"surface": "plan", "accepted": True, "reason": "accepted", "score": 0.9, "weakest_path": "grounding"}, root=tmp_path)
    append_quality({"surface": "npc", "accepted": False, "reason": "low_score", "score": 0.3, "weakest_path": "behavior"}, root=tmp_path)
    append_repair({"surface": "forge", "ok": 1, "before": {"reason": "low_score"}, "after": {"reason": "accepted", "score": 0.8, "weakest_path": "world_map.gd"}, "actions": [{"path": "world_map.gd"}], "targeted_path": "world_map.gd"}, root=tmp_path)
    Organismer(root=tmp_path, persist=False, galaxy=GalaxySystem())
    card = product_card.__wrapped__() if hasattr(product_card, "__wrapped__") else product_card()
    assert "quality" in card
    assert "repair_view" in card
    assert "repair_stats" in card

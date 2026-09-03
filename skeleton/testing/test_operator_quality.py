"""Operator quality surface tests."""
from __future__ import annotations


def test_product_card_exposes_quality(tmp_path):
    from skeleton.organism.product import product_card
    from skeleton.organism.quality_state import append_quality

    append_quality({"surface": "plan", "accepted": True, "reason": "accepted", "score": 0.9, "weakest_path": "grounding"}, root=tmp_path)
    append_quality({"surface": "npc", "accepted": False, "reason": "low_score", "score": 0.3, "weakest_path": "behavior"}, root=tmp_path)
    from skeleton.organism.organismer import Organismer
    from skeleton.galaxy.system import GalaxySystem
    org = Organismer(root=tmp_path, persist=False, galaxy=GalaxySystem())
    card = product_card.__wrapped__() if hasattr(product_card, "__wrapped__") else product_card()
    assert "quality" in card


def test_nervous_card_exposes_quality_pressure(tmp_path):
    from skeleton.galaxy.system import GalaxySystem
    from skeleton.organism.nervous import nervous_card
    from skeleton.organism.organismer import Organismer
    from skeleton.organism.quality_state import append_quality
    append_quality({"surface": "plan", "accepted": False, "reason": "low_score", "score": 0.2, "weakest_path": "grounding"}, root=tmp_path)
    org = Organismer(root=tmp_path, persist=False, galaxy=GalaxySystem())
    card = nervous_card(org)
    assert "quality" in card
    assert "quality_pressure" in card


def test_doctor_card_exposes_quality(tmp_path):
    from skeleton.galaxy.system import GalaxySystem
    from skeleton.organism.doctor import doctor_card
    from skeleton.organism.organismer import Organismer
    from skeleton.organism.quality_state import append_quality
    append_quality({"surface": "dialogue", "accepted": True, "reason": "accepted", "score": 0.8, "weakest_path": "branching"}, root=tmp_path)
    org = Organismer(root=tmp_path, persist=False, galaxy=GalaxySystem())
    card = doctor_card(org)
    assert "quality" in card
    assert "quality_pressure" in card


def test_satellites_card_exposes_quality(tmp_path):
    from skeleton.organism.satellites import satellites_card
    from skeleton.organism.quality_state import append_quality
    from skeleton.organism.organismer import Organismer
    from skeleton.galaxy.system import GalaxySystem
    append_quality({"surface": "game_logic", "accepted": True, "reason": "accepted", "score": 0.9, "weakest_path": "grounding"}, root=tmp_path)
    org = Organismer(root=tmp_path, persist=False, galaxy=GalaxySystem())
    card = satellites_card(org)
    assert "quality" in card
    assert card["quality"]["rollup"]["count"] >= 1

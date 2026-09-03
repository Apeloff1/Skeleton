"""Operator quality surface tests."""
from __future__ import annotations


def test_product_card_exposes_quality():
    from skeleton.organism.product import product_card
    card = product_card()
    assert card["quality"]["rollup"]["count"] >= 2
    assert "plan" in card["quality"]
    assert "pipeline" in card["quality"]


def test_nervous_card_exposes_quality_pressure(tmp_path):
    from skeleton.galaxy.system import GalaxySystem
    from skeleton.organism.nervous import nervous_card
    from skeleton.organism.organismer import Organismer
    org = Organismer(root=tmp_path, persist=False, galaxy=GalaxySystem())
    card = nervous_card(org)
    assert "quality" in card
    assert "quality_pressure" in card


def test_doctor_card_exposes_quality(tmp_path):
    from skeleton.galaxy.system import GalaxySystem
    from skeleton.organism.doctor import doctor_card
    from skeleton.organism.organismer import Organismer
    org = Organismer(root=tmp_path, persist=False, galaxy=GalaxySystem())
    card = doctor_card(org)
    assert "quality" in card
    assert "quality_pressure" in card


def test_satellites_card_exposes_quality():
    from skeleton.organism.satellites import satellites_card
    card = satellites_card()
    assert "quality" in card
    assert card["quality"]["rollup"]["count"] >= 2

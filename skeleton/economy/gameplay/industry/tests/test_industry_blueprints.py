"""Blueprint validation, efficiency math and chain planning."""

from __future__ import annotations

import pytest

from skeleton.economy.gameplay.industry.blueprints import Blueprint, BlueprintBook
from skeleton.economy.gameplay.industry.errors import IndustryError
from skeleton.economy.gameplay.industry.tests.conftest import BLUEPRINTS
from skeleton.simulation.economy.sim import EconomySimError


def test_materials_round_waste_up_and_research_lowers_it():
    bp = BLUEPRINTS[0]
    assert bp.materials(1) == {
        "coal": {"used": 1, "lost": 1},
        "ore": {"used": 3, "lost": 1},
    }
    assert bp.materials(10) == {
        "coal": {"used": 10, "lost": 1},
        "ore": {"used": 30, "lost": 3},
    }
    assert bp.waste_at(5) == 500
    assert bp.waste_at(10) == 0
    assert bp.waste_at(99) == 0  # clamped at max_research
    assert bp.materials(10, me_level=10)["ore"]["lost"] == 0


def test_time_efficiency_and_floor():
    bp = BLUEPRINTS[0]
    assert bp.ticks_at(0, 3) == 30
    assert bp.ticks_at(5, 1) == 8
    tiny = Blueprint("t", "b", 1, (("a", 1),), base_ticks=1, max_research=2)
    assert tiny.ticks_at(2) == 1


@pytest.mark.parametrize(
    "kw",
    [
        {"inputs": ()},
        {"inputs": (("x", 1), ("x", 2))},
        {"inputs": (("out", 1),)},
        {"waste_bps": 6_000},
        {"te_step_bps": 1_000},
        {"base_ticks": 0},
    ],
)
def test_bad_blueprints_refused(kw):
    # IndustryError subclasses EconomySimError, the base for all validation errors
    base = dict(
        blueprint_id="b", output="out", output_qty=1, inputs=(("x", 1),), base_ticks=5
    )
    base.update(kw)
    with pytest.raises(EconomySimError):
        Blueprint(**base)


def test_book_refuses_cycles_duplicates_and_unknown_items():
    book = BlueprintBook([Blueprint("a2b", "b", 1, (("a", 1),), base_ticks=1)])
    with pytest.raises(IndustryError):
        book.add(Blueprint("b2a", "a", 1, (("b", 1),), base_ticks=1))
    assert "b2a" not in book and book.producer("a") is None
    with pytest.raises(IndustryError):
        book.add(Blueprint("a2b", "c", 1, (("a", 1),), base_ticks=1))
    with pytest.raises(IndustryError):
        book.add(Blueprint("x2b", "b", 1, (("x", 1),), base_ticks=1))
    with pytest.raises(IndustryError):
        BlueprintBook([Blueprint("q", "b", 1, (("zz", 1),), base_ticks=1)], items={"b"})


def test_plan_expands_chain_deepest_first():
    book = BlueprintBook(BLUEPRINTS)
    plan = book.plan("hull", 2)
    assert [(s.blueprint_id, s.runs) for s in plan.steps] == [
        ("smelt_ingot", 17),
        ("press_plate", 4),
        ("weld_hull", 2),
    ]
    # plates: 8 -> 4 runs of 2; ingots: 4 for hulls + 12 for plates + 1 waste (5% of 12 rounds up)
    # ore: 17*3 = 51 + 6 waste; coal: 17 + 2 waste
    assert plan.raw == {"coal": 19, "ore": 57}
    assert plan.lost == {"coal": 2, "ingot": 1, "ore": 6}
    assert book.depth("hull") == 3 and book.depth("ore") == 0


def test_plan_uses_research_levels_and_is_pure():
    book = BlueprintBook(BLUEPRINTS)
    lean = book.plan("hull", 2, {"smelt_ingot": (10, 0), "press_plate": (10, 0)})
    assert lean.lost == {}
    assert lean.raw == {"coal": 16, "ore": 48}
    assert book.plan("hull", 2).to_dict() == book.plan("hull", 2).to_dict()
    with pytest.raises(IndustryError):
        book.plan("ore", 1)


def test_round_trip_state():
    book = BlueprintBook(BLUEPRINTS)
    again = BlueprintBook.from_state(book.to_state())
    assert again.to_state() == book.to_state()

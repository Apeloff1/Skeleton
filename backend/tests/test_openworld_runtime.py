from datetime import UTC, datetime, timedelta

import pytest

from core.crafting_engine import CraftOutput, CraftingError, Ingredient, Recipe, Workshop
from core.crew_runtime import CrewMember, CrewRole, CrewRoster
from core.voyage_runtime import Hazard, VesselSpec, VesselState, VoyageLeg, VoyageSimulator


def test_workshop_consumes_materials_and_collects_output():
    recipe = Recipe(
        id="repair-kit",
        category="equipment",
        ingredients=(Ingredient("wood", 2), Ingredient("line", 1)),
        output=CraftOutput("repair_kit", 3),
        craft_seconds=30,
        xp_reward=20,
    )
    workshop = Workshop((recipe,))
    workshop.add_item("wood", 2)
    workshop.add_item("line", 1)
    now = datetime(2026, 9, 14, tzinfo=UTC)
    job = workshop.start("repair-kit", slot=0, now=now)
    assert workshop.inventory == {}
    with pytest.raises(CraftingError, match="not complete"):
        workshop.collect(0, now=now + timedelta(seconds=29))
    output = workshop.collect(0, now=now + timedelta(seconds=30))
    assert output.item == "repair_kit"
    assert workshop.inventory["repair_kit"] == 3
    assert workshop.crafting_xp == 20


def test_workshop_cancel_refunds_exact_materials():
    recipe = Recipe(
        id="bait",
        category="bait",
        ingredients=(Ingredient("worm", 2),),
        output=CraftOutput("bait", 5),
        craft_seconds=5,
    )
    workshop = Workshop((recipe,))
    workshop.add_item("worm", 2)
    workshop.start("bait", slot=0)
    assert workshop.cancel(0) == {"worm": 2}
    assert workshop.inventory["worm"] == 2


def test_voyage_special_ability_reduces_matching_hazard():
    spec = VesselSpec(
        id="storm-chaser",
        tier=2,
        speed=6,
        durability=120,
        cargo_capacity=100,
        crew_capacity=5,
        max_sea_minutes=180,
        special_ability="storm_resistant",
    )
    state = VesselState(spec=spec, crew=2)
    sim = VoyageSimulator(state)
    result = sim.run_leg(VoyageLeg("strait", distance=20, difficulty=3, hazard=Hazard.STORM, reward_gold=50))
    assert result.completed is True
    assert result.hull_damage == pytest.approx(1.5)
    assert sim.gold == 50


def test_voyage_fails_before_mutation_when_supplies_insufficient():
    spec = VesselSpec("raft", 1, 2, 20, 10, 1, 30)
    state = VesselState(spec=spec, crew=1, food=0.1, water=100)
    sim = VoyageSimulator(state)
    before_hull = state.hull
    result = sim.run_leg(VoyageLeg("long", distance=20))
    assert result.completed is False
    assert "food" in result.reason
    assert state.hull == before_hull
    assert state.sea_minutes == 0


def test_crew_role_limits_and_effective_bonuses():
    navigator = CrewRole("navigator", max_per_ship=1, salary=45, bonuses={"travel_speed": 15})
    roster = CrewRoster(capacity=3)
    roster.enlist(CrewMember("nav-1", navigator, level=2))
    assert roster.payroll() == 45
    assert roster.aggregate_bonuses()["travel_speed"] == pytest.approx(15.75)
    with pytest.raises(RuntimeError, match="role limit"):
        roster.enlist(CrewMember("nav-2", navigator))
    roster.tick_condition(morale_delta=-50)
    assert roster.aggregate_bonuses()["travel_speed"] < 15.75


def test_crew_capacity_is_enforced():
    deckhand = CrewRole("deckhand", max_per_ship=10, salary=15, bonuses={"work_efficiency": 5})
    roster = CrewRoster(capacity=1)
    roster.enlist(CrewMember("a", deckhand))
    with pytest.raises(RuntimeError, match="capacity"):
        roster.enlist(CrewMember("b", deckhand))

from datetime import datetime, timezone

import pytest

from skeleton.frontier.aquarium import (
    add_fish,
    decoration_from_record,
    initial_aquarium,
    place_decoration,
    purchase_decoration,
    purchase_tank,
    quote_tank_purchase,
    remove_fish,
    set_theme,
    tank_from_record,
)
from skeleton.frontier.aquarium_models import AquariumPosition, AquariumTankSpec, DecorationSpec, DisplayFish
from skeleton.frontier.aquarium_state import AquariumState, AquariumTankState


def _fish(identity: str, *, x: int = 50, y: int = 50) -> DisplayFish:
    return DisplayFish(identity, "Blue Fish", "blue_fish", 20, AquariumPosition(x, y))


def test_source_starter_zero_cost_normalizes_to_empty_cost():
    tank = tank_from_record({"id": "starter", "name": "Starter Tank", "capacity": 10, "cost": 0, "unlock_level": 1, "decorations_allowed": 3})
    assert tank.cost == {}


def test_positions_and_fish_size_fail_closed():
    with pytest.raises(ValueError, match="0..100"):
        AquariumPosition(101, 50)
    with pytest.raises(TypeError, match="integer"):
        AquariumPosition(True, 50)
    with pytest.raises(ValueError, match="finite"):
        DisplayFish("bad", "Bad", "bad", float("nan"), AquariumPosition(1, 1))


def test_tank_purchase_checks_level_and_wallet_without_mutation():
    state = initial_aquarium()
    tank = AquariumTankSpec("medium", "Medium", 25, 10, 6, {"coins": 5000})
    with pytest.raises(ValueError, match="requires level 10"):
        quote_tank_purchase(state, tank, user_level=9, wallet={"coins": 9999})
    assert quote_tank_purchase(state, tank, user_level=10, wallet={"coins": 4999}).affordable is False
    assert quote_tank_purchase(state, tank, user_level=10, wallet={"coins": 5000}).affordable is True
    purchased = purchase_tank(state, tank)
    assert "medium" in purchased.owned_tanks and "medium" in purchased.tanks


def test_duplicate_fish_identity_cannot_be_displayed_twice():
    starter = AquariumTankSpec("starter", "Starter", 10, 1, 3)
    first = add_fish(initial_aquarium(), starter, _fish("fish-1"))
    with pytest.raises(ValueError, match="already displayed"):
        add_fish(first.aquarium, starter, _fish("fish-1"))


def test_capacity_and_total_count_remain_consistent():
    starter = AquariumTankSpec("starter", "Starter", 1, 1, 3)
    first = add_fish(initial_aquarium(), starter, _fish("fish-1"))
    assert first.aquarium.total_fish_displayed == 1
    with pytest.raises(ValueError, match="capacity"):
        add_fish(first.aquarium, starter, _fish("fish-2"))
    removed = remove_fish(first.aquarium, fish_id="fish-1")
    assert removed.aquarium.total_fish_displayed == 0


def test_duplicate_decoration_inventory_consumes_exactly_one():
    starter = AquariumTankSpec("starter", "Starter", 10, 1, 3)
    decoration = DecorationSpec("seaweed", "Seaweed", "plant", {"coins": 100})
    state = purchase_decoration(initial_aquarium(), decoration, quantity=2)
    placed = place_decoration(
        state,
        starter,
        decoration,
        position=AquariumPosition(10, 20),
        now=datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc),
        identity=lambda: "placed-1",
    )
    assert placed.aquarium.owned_decorations["seaweed"] == 1


def test_duplicate_placed_identity_is_rejected():
    starter = AquariumTankSpec("starter", "Starter", 10, 1, 3)
    decoration = decoration_from_record({"id": "seaweed", "name": "Seaweed", "category": "plant", "cost": {"coins": 100}})
    state = purchase_decoration(initial_aquarium(), decoration, quantity=2)
    first = place_decoration(state, starter, decoration, position=AquariumPosition(10, 20), now=datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc), identity=lambda: "same")
    with pytest.raises(ValueError, match="identity already exists"):
        place_decoration(first.aquarium, starter, decoration, position=AquariumPosition(20, 30), now=datetime(2026, 9, 15, 12, 1, tzinfo=timezone.utc), identity=lambda: "same")


def test_theme_selection_uses_explicit_allowlist():
    state = set_theme(initial_aquarium(), tank_id="starter", theme_id="night", allowed_themes=("ocean", "night"))
    assert state.tanks["starter"].theme == "night"
    with pytest.raises(ValueError, match="not available"):
        set_theme(state, tank_id="starter", theme_id="gold", allowed_themes=("ocean", "night"))


def test_total_count_mismatch_fails_closed():
    with pytest.raises(ValueError, match="must match"):
        AquariumState(tanks={"starter": AquariumTankState("starter", fish=(_fish("fish-1"),))}, owned_tanks=frozenset({"starter"}), total_fish_displayed=0)

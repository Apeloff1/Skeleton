from datetime import date, datetime, timezone

import pytest

from skeleton.frontier.aquarium import (
    AquariumDecorationSpec,
    AquariumLikeLedger,
    AquariumPosition,
    AquariumTankSpec,
    DisplayFish,
    add_fish,
    initial_aquarium,
    place_decoration,
    purchase_decoration,
    purchase_tank,
    record_like,
    tank_from_record,
)

NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)


def _starter() -> AquariumTankSpec:
    return AquariumTankSpec("starter", "Starter", 10, 100, 50, 3)


def _fish(identity: str = "fish-1") -> DisplayFish:
    return DisplayFish(
        identity,
        "Blue Fish",
        "blue_fish",
        20,
        "#4A90D9",
        {},
        AquariumPosition(50, 50),
        NOW,
    )


def test_source_starter_zero_cost_and_size_normalize_without_catalog_coupling():
    tank = tank_from_record(
        {
            "id": "starter",
            "name": "Starter Tank",
            "capacity": 10,
            "size": {"width": 100, "height": 50},
            "cost": 0,
            "unlock_level": 1,
            "decorations_allowed": 3,
        }
    )
    assert tank.cost == {}
    assert (tank.width, tank.height) == (100, 50)


def test_display_positions_fail_closed_outside_normalized_plane():
    with pytest.raises(ValueError, match="0..100"):
        AquariumPosition(101, 50)
    with pytest.raises(TypeError, match="integer"):
        AquariumPosition(True, 50)


def test_tank_purchase_checks_level_and_balance_without_mutating_wallet():
    medium = AquariumTankSpec(
        "medium",
        "Medium",
        25,
        200,
        80,
        6,
        unlock_level=10,
        cost={"coins": 5000},
    )
    state = initial_aquarium()
    balances = {"coins": 5000}

    with pytest.raises(ValueError, match="requires level 10"):
        purchase_tank(state, medium, user_level=9, balances=balances)
    with pytest.raises(ValueError, match="insufficient aquarium purchase balance"):
        purchase_tank(state, medium, user_level=10, balances={"coins": 4999})

    plan = purchase_tank(state, medium, user_level=10, balances=balances)
    assert plan.cost == {"coins": 5000}
    assert balances == {"coins": 5000}
    assert plan.aquarium.owned_tanks == frozenset({"starter", "medium"})
    assert set(plan.aquarium.tanks) == {"starter", "medium"}


def test_duplicate_fish_identity_is_rejected_and_count_is_derived():
    first = add_fish(initial_aquarium(), _starter(), _fish()).aquarium
    assert first.total_fish_displayed == 1
    with pytest.raises(ValueError, match="fish already displayed"):
        add_fish(first, _starter(), _fish())


def test_decoration_placement_consumes_exactly_one_duplicate_copy():
    decoration = AquariumDecorationSpec(
        "seaweed",
        "Seaweed",
        "plant",
        {"coins": 100},
        icon="plant",
    )
    purchase = purchase_decoration(
        initial_aquarium(),
        decoration,
        balances={"coins": 200},
        quantity=2,
    )
    assert purchase.aquarium.owned_decorations == {"seaweed": 2}

    placed = place_decoration(
        purchase.aquarium,
        _starter(),
        decoration,
        placement_id="placed-1",
        position=AquariumPosition(10, 20),
        placed_at=NOW,
    )
    assert placed.aquarium.owned_decorations == {"seaweed": 1}
    assert placed.aquarium.total_decorations_placed == 1


def test_daily_like_ledger_rejects_duplicate_identity_for_same_day():
    liked_on = date(2026, 9, 15)
    state, ledger = record_like(
        initial_aquarium(),
        AquariumLikeLedger(),
        liker_id="visitor-1",
        liked_on=liked_on,
    )
    assert state.likes == 1

    with pytest.raises(ValueError, match="already liked"):
        record_like(state, ledger, liker_id="visitor-1", liked_on=liked_on)

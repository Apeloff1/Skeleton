from __future__ import annotations

import random

import pytest

from skeleton.frontier.ship import (
    aggregate_crew,
    can_afford,
    can_hire,
    choose_crew_name,
    crew_role_from_record,
    generate_crew_dialogue,
    hiring_cost,
    quote_purchase,
    stores_for_location,
)


def _role(role: str, **overrides):
    base = {
        "title": role.replace("_", " ").title(),
        "name_pool": ["Morgan", "Drake"],
        "abilities": ["navigation_boost"],
        "max_per_ship": 1,
        "salary": 50,
        "skill_bonuses": {"navigation": 10, "crew_efficiency": 15},
        "dialogue_style": "professional_loyal",
    }
    base.update(overrides)
    return crew_role_from_record(role, base)


def test_crew_role_adapter_preserves_policy_and_metadata():
    role = _role("first_mate")

    assert role.role == "first_mate"
    assert role.max_per_ship == 1
    assert role.salary == 50
    assert role.abilities == ("navigation_boost",)
    assert role.skill_bonuses == {"navigation": 10, "crew_efficiency": 15}
    assert role.metadata["dialogue_style"] == "professional_loyal"
    assert hiring_cost(role) == 500
    assert can_hire(0, role)
    assert not can_hire(1, role)


def test_crew_name_generation_is_injected_and_deterministic():
    role = _role("first_mate")
    assert choose_crew_name(role, rng=random.Random(2)) == choose_crew_name(
        role,
        rng=random.Random(2),
    )


def test_crew_aggregation_combines_source_skill_bonuses_and_salary():
    first_mate = _role("first_mate")
    deckhand = _role(
        "deckhand",
        max_per_ship=10,
        salary=15,
        skill_bonuses={"fishing_speed": 5, "crew_efficiency": 5},
    )
    summary = aggregate_crew(
        [
            {"role": "first_mate", "salary": 50},
            {"role": "deckhand", "salary": 15},
            {"role": "deckhand", "salary": 15},
        ],
        {"first_mate": first_mate, "deckhand": deckhand},
    )

    assert summary == {
        "total_crew": 3,
        "total_bonuses": {
            "navigation": 10,
            "crew_efficiency": 25,
            "fishing_speed": 10,
        },
        "daily_salary": 80,
        "role_counts": {"first_mate": 1, "deckhand": 2},
    }


def test_crew_aggregation_fails_closed_on_role_limit_or_unknown_role():
    first_mate = _role("first_mate")
    with pytest.raises(ValueError, match="crew role limit exceeded"):
        aggregate_crew(
            [{"role": "first_mate"}, {"role": "first_mate"}],
            {"first_mate": first_mate},
        )
    with pytest.raises(KeyError, match="unknown crew role"):
        aggregate_crew([{"role": "ghost"}], {"first_mate": first_mate})


def test_crew_dialogue_preserves_morale_bands_and_role_story():
    navigator = _role("navigator")

    high = generate_crew_dialogue({"name": "Stars", "morale": 90}, navigator)
    medium = generate_crew_dialogue({"name": "Stars", "morale": 60}, navigator)
    low = generate_crew_dialogue({"name": "Stars", "morale": 20}, navigator)

    assert "Ready for anything" in high["status"]
    assert "shore leave" in medium["status"]
    assert "wearing thin" in low["status"]
    assert "constellation" in high["story"]
    assert high["greeting"] == "*Stars nods* Aye, Captain?"


def test_purchase_quote_preserves_markup_and_stock_rules():
    item = {"id": "emergency_rations", "price": 15, "quantity": 20}
    quote = quote_purchase(item, 2, markup=1.5)

    assert quote.item_id == "emergency_rations"
    assert quote.quantity == 2
    assert quote.unit_price == 15
    assert quote.total_price == 45
    assert can_afford(45, quote)
    assert not can_afford(44, quote)

    with pytest.raises(ValueError, match="not enough stock"):
        quote_purchase(item, 21, markup=1.5)
    with pytest.raises(ValueError, match="purchase quantity must be positive"):
        quote_purchase(item, 0)


def test_location_store_policy_adds_port_and_pirate_conditionals():
    catalog = {
        store_id: {"id": store_id, "name": store_id}
        for store_id in (
            "general_store",
            "bait_shop",
            "tavern",
            "fish_market",
            "shipyard",
            "black_market",
        )
    }

    ordinary = stores_for_location("quiet_bay", catalog)
    port = stores_for_location("port_prosperity", catalog)
    pirate_haven = stores_for_location("pirate_haven", catalog)

    assert [store["id"] for store in ordinary] == [
        "general_store",
        "bait_shop",
        "tavern",
        "fish_market",
    ]
    assert [store["id"] for store in port][-1] == "shipyard"
    assert [store["id"] for store in pirate_haven][-1] == "black_market"

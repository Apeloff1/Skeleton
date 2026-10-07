from __future__ import annotations

import pytest

from skeleton.frontier.equipment import (
    EquipmentLoadout,
    apply_equipment_purchase,
    calculate_equipment_bonuses,
    equip_item,
    equipment_from_record,
    equipment_matches_biotope,
    quote_equipment_purchase,
    recommended_equipment,
)


def _record(
    *,
    item_id="surf_rod",
    category="rod",
    biotope="saltwater",
    bonuses=None,
    cost=None,
    unlock_level=15,
):
    return {
        "id": item_id,
        "name": item_id.replace("_", " ").title(),
        "category": category,
        "biotope": biotope,
        "stats": {"power": 60},
        "bonuses": bonuses or {},
        "cost": cost or {"coins": 2500},
        "unlock_level": unlock_level,
        "rarity": "uncommon",
    }


def test_equipment_normalization_and_biotope_matching():
    item = equipment_from_record(_record())
    assert item.category == "rod"
    assert equipment_matches_biotope(item, "saltwater")
    assert not equipment_matches_biotope(item, "river")

    universal = equipment_from_record(
        _record(
            item_id="basic_rod",
            biotope="universal",
            unlock_level=1,
            cost={"coins": 0},
        )
    )
    assert equipment_matches_biotope(universal, "river")


def test_purchase_quote_is_mutation_free_and_tracks_missing_funds():
    item = equipment_from_record(_record())
    loadout = EquipmentLoadout()

    blocked = quote_equipment_purchase(
        item,
        loadout,
        {"coins": 1000},
        user_level=10,
    )
    assert blocked.missing_funds == {"coins": 1500}
    assert not blocked.can_purchase

    allowed = quote_equipment_purchase(
        item,
        loadout,
        {"coins": 3000},
        user_level=20,
    )
    assert allowed.can_purchase

    owned = apply_equipment_purchase(loadout, item)
    assert item.id in owned.owned_rods
    assert item.id not in loadout.owned_rods
    with pytest.raises(ValueError, match="already owned"):
        apply_equipment_purchase(owned, item)


def test_equip_requires_ownership_and_preserves_other_loadout_state():
    item = equipment_from_record(_record())
    loadout = EquipmentLoadout()
    with pytest.raises(ValueError, match="not owned"):
        equip_item(loadout, item)

    owned = apply_equipment_purchase(loadout, item)
    equipped = equip_item(owned, item)
    assert equipped.equipped_rod == item.id
    assert equipped.owned_rods == frozenset({item.id})


def test_bonus_aggregation_preserves_source_key_semantics():
    rod = equipment_from_record(
        _record(
            bonuses={
                "saltwater_catch_rate": 1.2,
                "rare_fish_chance": 1.3,
                "saltwater_distance": 1.1,
                "fighting_power": 1.4,
            }
        )
    )
    line = equipment_from_record(
        _record(
            item_id="line",
            category="line",
            bonuses={"stealth_bonus": 1.1, "sensitivity_bonus": 1.2},
        )
    )
    bobber = equipment_from_record(
        _record(
            item_id="bobber",
            category="bobber",
            bonuses={"bite_detection": 1.5, "panfish_bonus": 1.3},
        )
    )

    bonuses = calculate_equipment_bonuses(
        rod,
        line,
        bobber,
        biotope="saltwater",
    )
    assert bonuses.catch_rate == pytest.approx(1.2 * 1.1 * 1.1 * 1.3)
    assert bonuses.rare_chance == pytest.approx(1.3)
    assert bonuses.cast_distance == pytest.approx(1.1)
    assert bonuses.fighting_power == pytest.approx(1.4)
    assert bonuses.sensitivity == pytest.approx(1.2 * 1.5)


def test_recommendation_filter_can_include_universal_without_catalog_copy():
    exact = equipment_from_record(_record())
    universal = equipment_from_record(
        _record(
            item_id="basic_rod",
            biotope="universal",
            unlock_level=1,
            cost={"coins": 0},
        )
    )

    assert recommended_equipment(
        [exact, universal],
        biotope="saltwater",
    ) == (exact,)
    assert recommended_equipment(
        [exact, universal],
        biotope="saltwater",
        include_universal=True,
    ) == (exact, universal)

    with pytest.raises(ValueError, match="duplicate equipment id"):
        recommended_equipment([exact, exact], biotope="saltwater")


def test_equipment_boundaries_fail_closed():
    with pytest.raises(ValueError, match="unsupported equipment category"):
        equipment_from_record(_record(category="boat"))
    with pytest.raises(ValueError, match="must be finite"):
        equipment_from_record(_record(bonuses={"bad": float("nan")}))
    with pytest.raises(ValueError, match="must reference owned"):
        EquipmentLoadout(equipped_rod="ghost")

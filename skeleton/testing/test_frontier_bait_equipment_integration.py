from __future__ import annotations

from dataclasses import asdict

import pytest

from skeleton.frontier.bait import CatchBonuses, combine_external_bonuses
from skeleton.frontier.equipment import EquipmentSpec, calculate_equipment_bonuses


def test_equipment_bonuses_compose_into_fishing_boundary():
    rod = EquipmentSpec(
        id="surf_rod",
        name="Surf Rod",
        category="rod",
        biotope="saltwater",
        bonuses={
            "saltwater_catch_rate": 1.15,
            "rare_fish_chance": 1.3,
            "fighting_power": 1.5,
        },
    )
    line = EquipmentSpec(
        id="stealth_line",
        name="Stealth Line",
        category="line",
        biotope="universal",
        bonuses={"stealth": 1.2, "sensitivity": 1.1},
    )
    bobber = EquipmentSpec(
        id="salt_bobber",
        name="Salt Bobber",
        category="bobber",
        biotope="saltwater",
        bonuses={"bite_detection": 1.4, "offshore_bonus": 1.25},
    )
    equipment = calculate_equipment_bonuses(
        rod,
        line,
        bobber,
        biotope="saltwater",
    )
    combined = combine_external_bonuses(
        CatchBonuses(catch_rate=2.0, rare_chance=1.5),
        asdict(equipment),
    )
    assert combined.catch_rate == pytest.approx(2.0 * equipment.catch_rate)
    assert combined.rare_chance == pytest.approx(1.5 * equipment.rare_chance)
    assert combined.legendary_chance == pytest.approx(1.0)

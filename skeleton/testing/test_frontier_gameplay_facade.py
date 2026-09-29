from __future__ import annotations

import skeleton.frontier.gameplay as gameplay


def test_gameplay_facade_exposes_collision_free_promoted_surface():
    assert gameplay.BaitSpec.__module__ == "skeleton.frontier.ecology.bait"
    assert gameplay.BreedingJob.__module__ == "skeleton.frontier.ecology.breeding"
    assert gameplay.CraftingRecipe.__module__ == "skeleton.frontier.economy.crafting"
    assert gameplay.EnergyState.__module__ == "skeleton.frontier.economy.energy"
    assert gameplay.EquipmentSpec.__module__ == "skeleton.frontier.economy.equipment"
    assert gameplay.breeding_speed_up_cost.__module__ == "skeleton.frontier.ecology.breeding"
    assert gameplay.start_craft.__module__ == "skeleton.frontier.economy.crafting"


def test_gameplay_facade_bait_and_equipment_composition_is_available():
    equipment = gameplay.EquipmentBonuses(catch_rate=1.25, rare_chance=1.2)
    fishing = gameplay.CatchBonuses(catch_rate=1.5, rare_chance=1.1)
    combined = gameplay.combine_external_bonuses(
        fishing,
        {
            "catch_rate": equipment.catch_rate,
            "rare_chance": equipment.rare_chance,
        },
    )
    assert combined.catch_rate == 1.875
    assert combined.rare_chance == 1.32

from __future__ import annotations

import pytest

from skeleton.frontier.crafting import recipe_from_record
from skeleton.frontier.crafting_adapters import energy_booster_from_craft_output


def _recipe(effect):
    return recipe_from_record(
        {
            "id": "energy_drink",
            "name": "Energy Drink",
            "category": "consumable",
            "ingredients": [{"item": "fresh_water", "quantity": 2}],
            "output": {
                "item": "energy_drink",
                "quantity": 2,
                "effect": effect,
            },
            "craft_time_seconds": 45,
            "xp_reward": 10,
            "unlock_level": 2,
        }
    )


def test_crafted_restore_effect_adapts_to_one_energy_booster_item():
    booster = energy_booster_from_craft_output(_recipe({"energy_restore": 25}))
    assert booster.id == "energy_drink"
    assert booster.name == "Energy Drink"
    assert booster.energy_restore == 25
    assert booster.infinite_duration_minutes == 0
    assert booster.regen_multiplier == 1.0


def test_crafted_timed_energy_effects_adapt_without_inventory_coupling():
    infinite = energy_booster_from_craft_output(
        _recipe({"infinite_duration_minutes": 60})
    )
    assert infinite.infinite_duration_minutes == 60

    regen = energy_booster_from_craft_output(
        _recipe({"regen_multiplier": 2.0, "duration_minutes": 30})
    )
    assert regen.regen_multiplier == 2.0
    assert regen.duration_minutes == 30


def test_unrelated_or_mixed_craft_effects_fail_closed():
    with pytest.raises(ValueError, match="no energy effect"):
        energy_booster_from_craft_output(_recipe({}))

    with pytest.raises(ValueError, match="canonical energy booster shape"):
        energy_booster_from_craft_output(
            _recipe({"xp_multiplier": 2.0, "duration_minutes": 10})
        )

    with pytest.raises(ValueError, match="canonical energy booster shape"):
        energy_booster_from_craft_output(
            _recipe({"energy_restore": 25, "xp_multiplier": 2.0})
        )


def test_invalid_energy_effect_value_is_rejected_by_canonical_energy_contract():
    with pytest.raises(TypeError, match="energy booster energy_restore"):
        energy_booster_from_craft_output(_recipe({"energy_restore": True}))

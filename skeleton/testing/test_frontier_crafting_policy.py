from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from skeleton.frontier.crafting import (
    WorkshopState,
    can_craft,
    cancel_craft,
    cancel_refund,
    collect_craft,
    crafting_xp_threshold,
    missing_materials,
    recipe_from_record,
    recipe_is_unlocked,
    refresh_workshop,
    speed_up_cost,
    speed_up_craft,
    start_craft,
    unlock_crafting_slot,
    unlock_slot_cost,
)


T0 = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)


def _record(**overrides):
    base = {
        "id": "basic_bait",
        "name": "Basic Bait",
        "category": "bait",
        "description": "Standard fishing bait",
        "ingredients": [
            {"item": "worm", "quantity": 3},
            {"item": "bread_crumb", "quantity": 1},
        ],
        "output": {"item": "basic_bait", "quantity": 5},
        "craft_time_seconds": 60,
        "xp_reward": 250,
        "unlock_level": 5,
        "icon": "x",
    }
    base.update(overrides)
    return base


def _recipe():
    return recipe_from_record(_record())


def test_recipe_normalizes_and_rejects_duplicate_ingredients():
    recipe = _recipe()
    assert recipe.category == "bait"
    assert recipe.output.quantity == 5

    duplicate = _record(
        ingredients=[
            {"item": "worm", "quantity": 1},
            {"item": "worm", "quantity": 2},
        ]
    )
    with pytest.raises(ValueError, match="duplicate craft ingredient"):
        recipe_from_record(duplicate)


def test_unlock_and_material_checks_are_pure_policy():
    recipe = _recipe()
    assert not recipe_is_unlocked(recipe, user_level=4)
    assert recipe_is_unlocked(
        recipe,
        user_level=4,
        unlocked_recipes=["basic_bait"],
    )
    assert missing_materials(recipe, {"worm": 2, "bread_crumb": 1}) == {"worm": 1}
    assert can_craft(
        recipe,
        {"worm": 3, "bread_crumb": 1},
        user_level=5,
    )


def test_start_plan_is_mutation_free_and_uses_source_timing_semantics():
    recipe = _recipe()
    workshop = WorkshopState(unlocked_recipes=frozenset({"basic_bait"}))
    materials = {"worm": 5, "bread_crumb": 2}

    plan = start_craft(
        workshop,
        recipe,
        materials,
        slot=0,
        user_level=1,
        now=T0,
    )

    assert materials == {"worm": 5, "bread_crumb": 2}
    assert plan.materials == {"worm": 2, "bread_crumb": 1}
    assert plan.job.complete_at == T0 + timedelta(seconds=60)
    assert workshop.crafting_slots[0] is None
    assert plan.workshop.crafting_slots[0] is not None


def test_refresh_and_collect_support_multiple_level_gains_safely():
    recipe = _recipe()
    workshop = WorkshopState(
        unlocked_recipes=frozenset({"basic_bait"}),
        crafting_xp=90,
    )
    plan = start_craft(
        workshop,
        recipe,
        {"worm": 3, "bread_crumb": 1},
        slot=0,
        user_level=1,
        now=T0,
    )

    with pytest.raises(ValueError, match="not complete"):
        collect_craft(
            plan.workshop,
            slot=0,
            now=T0 + timedelta(seconds=59),
        )

    refreshed = refresh_workshop(
        plan.workshop,
        now=T0 + timedelta(seconds=60),
    )
    assert refreshed.crafting_slots[0].status == "complete"

    collected = collect_craft(
        refreshed,
        slot=0,
        now=T0 + timedelta(seconds=60),
    )
    assert collected.workshop.total_crafted == 1
    assert collected.levels_gained == 2
    assert collected.workshop.crafting_level == 3
    assert collected.workshop.crafting_xp == 40


def test_speed_up_quote_and_completion_preserve_source_policy():
    recipe = recipe_from_record(_record(craft_time_seconds=121))
    plan = start_craft(
        WorkshopState(unlocked_recipes=frozenset({"basic_bait"})),
        recipe,
        {"worm": 3, "bread_crumb": 1},
        slot=0,
        user_level=1,
        now=T0,
    )

    assert speed_up_cost(plan.job, now=T0) == 2
    assert speed_up_cost(plan.job, now=T0 + timedelta(seconds=120)) == 1

    sped = speed_up_craft(
        plan.workshop,
        slot=0,
        now=T0 + timedelta(seconds=30),
    )
    assert sped.crafting_slots[0].status == "complete"
    assert sped.crafting_slots[0].complete_at == T0 + timedelta(seconds=30)


def test_cancel_uses_integer_floor_refund_and_binds_job_to_recipe():
    recipe = _recipe()
    assert cancel_refund(recipe) == {"worm": 1}

    plan = start_craft(
        WorkshopState(unlocked_recipes=frozenset({"basic_bait"})),
        recipe,
        {"worm": 3, "bread_crumb": 1},
        slot=0,
        user_level=1,
        now=T0,
    )
    other = recipe_from_record(_record(id="other", name="Other"))

    with pytest.raises(ValueError, match="does not match"):
        cancel_craft(plan.workshop, other, slot=0, now=T0)

    cancelled = cancel_craft(plan.workshop, recipe, slot=0, now=T0)
    assert cancelled.returned_materials == {"worm": 1}
    assert cancelled.workshop.crafting_slots[0] is None

    completed = refresh_workshop(
        plan.workshop,
        now=T0 + timedelta(minutes=2),
    )
    with pytest.raises(ValueError, match="cannot cancel completed"):
        cancel_craft(
            completed,
            recipe,
            slot=0,
            now=T0 + timedelta(minutes=2),
        )


def test_slot_unlock_policy_preserves_cost_curve_and_maximum():
    assert unlock_slot_cost(2) == 200
    unlocked = unlock_crafting_slot(WorkshopState())
    assert unlocked.gem_cost == 200
    assert unlocked.workshop.max_slots == 3
    assert len(unlocked.workshop.crafting_slots) == 3

    maximum = WorkshopState(crafting_slots=(None,) * 5, max_slots=5)
    with pytest.raises(ValueError, match="maximum crafting slots"):
        unlock_crafting_slot(maximum)


def test_crafting_boundaries_reject_type_confusion_and_naive_time():
    recipe = _recipe()
    workshop = WorkshopState(unlocked_recipes=frozenset({"basic_bait"}))

    with pytest.raises(TypeError, match="slot must be an integer"):
        start_craft(
            workshop,
            recipe,
            {"worm": 3, "bread_crumb": 1},
            slot=True,
            user_level=1,
            now=T0,
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        start_craft(
            workshop,
            recipe,
            {"worm": 3, "bread_crumb": 1},
            slot=0,
            user_level=1,
            now=T0.replace(tzinfo=None),
        )
    with pytest.raises(ValueError, match="length must equal"):
        WorkshopState(crafting_slots=(None,), max_slots=2)


def test_craft_output_effect_is_preserved_for_cross_contract_adapters():
    recipe = recipe_from_record(
        _record(
            output={
                "item": "energy_drink",
                "quantity": 2,
                "effect": {"energy_restore": 25},
            }
        )
    )
    assert recipe.output.effect == {"energy_restore": 25}
    assert crafting_xp_threshold(3) == 300

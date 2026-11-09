from datetime import datetime, timedelta, timezone

import pytest

from skeleton.frontier.cooking import (
    FishInventoryItem,
    KitchenState,
    active_buffs,
    collect_dish,
    ingredient_purchase_cost,
    recipe_from_record,
    start_cooking,
)


def _now() -> datetime:
    return datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)


def _recipe():
    return recipe_from_record(
        {
            "id": "salmon_sashimi",
            "name": "Fresh Salmon Sashimi",
            "category": "raw",
            "difficulty": 3,
            "ingredients": [
                {
                    "type": "fish",
                    "fish_ids": ["chinook_salmon", "coho_salmon"],
                    "quantity": 1,
                    "min_size": 50,
                },
                {"type": "item", "item_id": "wasabi", "quantity": 1},
                {"type": "item", "item_id": "soy_sauce", "quantity": 1},
            ],
            "cooking_time_seconds": 30,
            "required_station": "prep_table",
            "unlock_level": 25,
            "rewards": {"xp": 100, "coins": 250, "dish_value": 500},
            "stats_boost": {
                "energy_restore": 25,
                "rare_fish_bonus": 1.15,
                "duration_minutes": 30,
            },
        }
    )


def test_recipe_normalization_preserves_fish_size_constraint_and_cost_planning():
    recipe = _recipe()
    fish_requirement = recipe.ingredients[0]
    assert fish_requirement.fish_ids == ("chinook_salmon", "coho_salmon")
    assert fish_requirement.min_size == 50.0
    assert ingredient_purchase_cost({"coins": 15}, 3) == {"coins": 45}


def test_start_cooking_consumes_exact_items_and_only_size_eligible_fish():
    recipe = _recipe()
    state = KitchenState(
        ingredients={"wasabi": 2, "soy_sauce": 1},
        unlocked_recipes=frozenset({recipe.id}),
    )
    fish = (
        FishInventoryItem(id="small", species="chinook_salmon", size=49.9),
        FishInventoryItem(id="eligible", species="coho_salmon", size=55),
    )

    plan = start_cooking(state, recipe, user_level=1, fish_inventory=fish, now=_now())

    assert plan.slot == 0
    assert plan.consumed_ingredients == {"wasabi": 1, "soy_sauce": 1}
    assert plan.remaining_ingredients == {"wasabi": 1, "soy_sauce": 0}
    assert plan.consumed_fish_ids == ("eligible",)
    assert tuple(item.id for item in plan.remaining_fish) == ("small",)
    assert plan.job.complete_at == _now() + timedelta(seconds=30)


def test_fish_cannot_be_reused_across_multiple_requirements():
    recipe = recipe_from_record(
        {
            "id": "double_fish",
            "name": "Double Fish",
            "category": "test",
            "difficulty": 1,
            "ingredients": [
                {"type": "fish", "fish_ids": ["bass"], "quantity": 1},
                {"type": "fish", "fish_ids": ["bass"], "quantity": 1},
            ],
            "cooking_time_seconds": 5,
            "required_station": "grill",
            "unlock_level": 1,
            "rewards": {},
            "stats_boost": {},
        }
    )
    with pytest.raises(ValueError, match="not enough eligible fish"):
        start_cooking(
            KitchenState(),
            recipe,
            user_level=1,
            fish_inventory=(FishInventoryItem(id="only", species="bass", size=10),),
            now=_now(),
        )


def test_duplicate_fish_identity_fails_closed():
    recipe = _recipe()
    state = KitchenState(
        ingredients={"wasabi": 1, "soy_sauce": 1},
        unlocked_recipes=frozenset({recipe.id}),
    )
    duplicate = FishInventoryItem(id="same", species="coho_salmon", size=60)
    with pytest.raises(ValueError, match="duplicate fish inventory id"):
        start_cooking(
            state,
            recipe,
            user_level=1,
            fish_inventory=(duplicate, duplicate),
            now=_now(),
        )


def test_collect_requires_completion_then_emits_rewards_and_expiring_buff():
    recipe = _recipe()
    state = KitchenState(
        ingredients={"wasabi": 1, "soy_sauce": 1},
        unlocked_recipes=frozenset({recipe.id}),
    )
    start = start_cooking(
        state,
        recipe,
        user_level=1,
        fish_inventory=(FishInventoryItem(id="fish", species="chinook_salmon", size=80),),
        now=_now(),
    )

    with pytest.raises(ValueError, match="not ready"):
        collect_dish(start.kitchen, recipe, slot=0, now=_now() + timedelta(seconds=29))

    collected = collect_dish(
        start.kitchen,
        recipe,
        slot=0,
        now=_now() + timedelta(seconds=30),
    )
    assert collected.rewards["coins"] == 250
    assert collected.xp_earned == 100
    assert collected.kitchen.dishes_cooked == 1
    assert collected.kitchen.cooking_xp == 100
    assert collected.kitchen.cooking_slots[0] is None
    assert collected.buff is not None
    assert collected.buff.effects["energy_restore"] == 25
    assert len(active_buffs(collected.kitchen, now=_now() + timedelta(minutes=30))) == 1
    assert active_buffs(collected.kitchen, now=_now() + timedelta(minutes=31)) == ()


def test_nonfinite_buff_values_fail_closed():
    with pytest.raises(ValueError, match="finite"):
        recipe_from_record(
            {
                "id": "bad",
                "name": "Bad",
                "category": "test",
                "difficulty": 1,
                "ingredients": [{"type": "item", "item_id": "salt", "quantity": 1}],
                "cooking_time_seconds": 1,
                "required_station": "kitchen",
                "unlock_level": 1,
                "rewards": {},
                "stats_boost": {"catch_bonus": float("nan"), "duration_minutes": 1},
            }
        )

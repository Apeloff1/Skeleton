from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from skeleton.frontier.cooking import (
    CookingJob,
    FishInventoryItem,
    KitchenState,
    collect_dish,
    cooking_recipe_digest,
    recipe_from_record,
    recipe_is_unlocked,
    start_cooking,
)


T0 = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)


def _record(**overrides):
    base = {
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
        ],
        "cooking_time_seconds": 30,
        "required_station": "prep_table",
        "unlock_level": 25,
        "rewards": {"xp": 100, "coins": 250},
        "stats_boost": {
            "energy_restore": 25,
            "rare_fish_bonus": 1.15,
            "duration_minutes": 30,
        },
    }
    base.update(overrides)
    return base


def _started():
    recipe = recipe_from_record(_record())
    state = KitchenState(
        ingredients={"wasabi": 1},
        unlocked_recipes=frozenset({recipe.id}),
    )
    plan = start_cooking(
        state,
        recipe,
        user_level=1,
        fish_inventory=(
            FishInventoryItem(id="fish", species="chinook_salmon", size=80),
        ),
        now=T0,
    )
    return recipe, plan


def test_job_binds_canonical_recipe_digest_at_start():
    recipe, plan = _started()

    assert plan.job.recipe_digest == cooking_recipe_digest(recipe)
    assert len(plan.job.recipe_digest) == 64
    assert plan.job.recipe_digest == plan.job.recipe_digest.lower()


def test_same_id_reward_tampering_is_rejected_at_collection():
    recipe, plan = _started()
    tampered = replace(recipe, rewards={"xp": 1_000_000, "coins": 9_999_999})

    with pytest.raises(ValueError, match="semantics do not match"):
        collect_dish(
            plan.kitchen,
            tampered,
            slot=0,
            now=T0 + timedelta(seconds=30),
        )


def test_same_id_buff_tampering_is_rejected_at_collection():
    recipe, plan = _started()
    tampered = replace(
        recipe,
        stats_boost={
            "energy_restore": 1_000_000,
            "rare_fish_bonus": 100.0,
            "duration_minutes": 10_000,
        },
    )

    with pytest.raises(ValueError, match="semantics do not match"):
        collect_dish(
            plan.kitchen,
            tampered,
            slot=0,
            now=T0 + timedelta(seconds=30),
        )


def test_exact_started_recipe_still_collects_normally():
    recipe, plan = _started()

    collected = collect_dish(
        plan.kitchen,
        recipe,
        slot=0,
        now=T0 + timedelta(seconds=30),
    )

    assert collected.rewards == {"xp": 100, "coins": 250}
    assert collected.xp_earned == 100
    assert collected.buff is not None
    assert collected.buff.effects["energy_restore"] == 25


def test_digest_is_stable_across_mapping_insertion_order():
    first = recipe_from_record(_record(rewards={"xp": 100, "coins": 250}))
    second = recipe_from_record(_record(rewards={"coins": 250, "xp": 100}))

    assert cooking_recipe_digest(first) == cooking_recipe_digest(second)


def test_job_rejects_malformed_recipe_digest():
    with pytest.raises(ValueError, match="SHA-256"):
        CookingJob(
            recipe_id="recipe",
            recipe_name="Recipe",
            recipe_digest="NOT-A-DIGEST",
            started_at=T0,
            complete_at=T0 + timedelta(seconds=1),
        )


def test_unlocked_recipe_boundary_rejects_string_collection_confusion():
    recipe = recipe_from_record(_record())

    with pytest.raises(TypeError, match="collection of strings"):
        recipe_is_unlocked(
            recipe,
            user_level=1,
            unlocked_recipes="salmon_sashimi",
        )


def test_recipe_record_rejects_description_and_icon_type_coercion():
    with pytest.raises(TypeError, match="description must be a string"):
        recipe_from_record(_record(description={"unsafe": "coercion"}))

    with pytest.raises(TypeError, match="icon must be a string"):
        recipe_from_record(_record(icon=123))

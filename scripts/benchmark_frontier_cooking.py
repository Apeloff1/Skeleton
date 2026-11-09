#!/usr/bin/env python3
"""Observational benchmark for promoted cooking/kitchen policy."""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import time
from typing import Any

from skeleton.frontier.cooking import (
    FishInventoryItem,
    KitchenState,
    collect_dish,
    cooking_recipe_digest,
    recipe_from_record,
    start_cooking,
)


SOURCE_SEMANTICS = {
    "primary_repository": "Apeloff1/Lorebuffa",
    "primary_path": "backend/cooking_routes.py",
    "primary_blob": "4c366d1c0baa89223758c28f0d4217d1dfa49bc9",
    "equivalent_repository": "Apeloff1/Openworld",
    "equivalent_path": "backend/cooking_routes.py",
    "equivalent_blob": "24575861b7120f036bd646a4ed94950ce27d45ce",
    "equivalence": "portable-policy-equivalent; presentation-only source divergence",
}


def _recipe():
    return recipe_from_record(
        {
            "id": "benchmark_grilled_bass",
            "name": "Benchmark Grilled Bass",
            "category": "grilled",
            "difficulty": 1,
            "ingredients": [
                {
                    "type": "fish",
                    "fish_ids": ["largemouth_bass", "sea_bass"],
                    "quantity": 1,
                },
                {"type": "item", "item_id": "lemon", "quantity": 1},
                {"type": "item", "item_id": "herbs", "quantity": 1},
            ],
            "cooking_time_seconds": 1,
            "required_station": "grill",
            "unlock_level": 1,
            "rewards": {"xp": 25, "coins": 50, "dish_value": 100},
            "stats_boost": {
                "energy_restore": 15,
                "duration_minutes": 10,
            },
        }
    )


def run_benchmark(*, iterations: int = 2000) -> dict[str, Any]:
    if isinstance(iterations, bool) or not isinstance(iterations, int):
        raise TypeError("iterations must be an integer")
    if iterations < 1:
        raise ValueError("iterations must be positive")

    recipe = _recipe()
    digest = cooking_recipe_digest(recipe)
    now = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)

    tamper_rejected = False
    tamper_plan = start_cooking(
        KitchenState(ingredients={"lemon": 1, "herbs": 1}),
        recipe,
        user_level=1,
        fish_inventory=(
            FishInventoryItem(id="tamper-fish", species="largemouth_bass", size=20),
        ),
        now=now,
    )
    try:
        collect_dish(
            tamper_plan.kitchen,
            replace(recipe, rewards={"xp": 999999, "coins": 999999}),
            slot=0,
            now=now + timedelta(seconds=1),
        )
    except ValueError as exc:
        tamper_rejected = "semantics do not match" in str(exc)
    if not tamper_rejected:
        raise AssertionError("same-id recipe tampering was not rejected")

    started = time.perf_counter_ns()
    xp_total = 0
    coins_total = 0
    buffs_created = 0
    consumed_fish = 0
    for index in range(iterations):
        state = KitchenState(ingredients={"lemon": 1, "herbs": 1})
        plan = start_cooking(
            state,
            recipe,
            user_level=1,
            fish_inventory=(
                FishInventoryItem(
                    id=f"fish-{index}",
                    species="largemouth_bass",
                    size=20,
                ),
            ),
            now=now,
        )
        if plan.job.recipe_digest != digest:
            raise AssertionError("job recipe digest changed during benchmark")
        collected = collect_dish(
            plan.kitchen,
            recipe,
            slot=0,
            now=now + timedelta(seconds=1),
        )
        xp_total += collected.xp_earned
        coins_total += collected.rewards["coins"]
        consumed_fish += len(plan.consumed_fish_ids)
        buffs_created += int(collected.buff is not None)

    elapsed_ns = time.perf_counter_ns() - started
    expected_xp = iterations * 25
    expected_coins = iterations * 50
    if xp_total != expected_xp:
        raise AssertionError("cooking XP accounting mismatch")
    if coins_total != expected_coins:
        raise AssertionError("cooking coin accounting mismatch")
    if consumed_fish != iterations:
        raise AssertionError("cooking fish consumption mismatch")
    if buffs_created != iterations:
        raise AssertionError("cooking buff creation mismatch")

    elapsed_seconds = elapsed_ns / 1_000_000_000
    return {
        "workload": "frontier-cooking-policy-v1",
        "source_semantics": SOURCE_SEMANTICS,
        "configuration": {"iterations": iterations},
        "evidence": {
            "recipe_digest": digest,
            "tamper_rejected": tamper_rejected,
            "xp_total": xp_total,
            "coins_total": coins_total,
            "consumed_fish": consumed_fish,
            "buffs_created": buffs_created,
            "invariants_hold": True,
        },
        "timing": {
            "elapsed_seconds": elapsed_seconds,
            "iterations_per_second": (
                iterations / elapsed_seconds if elapsed_seconds else None
            ),
            "latency_gate": False,
        },
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=2000)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    print(json.dumps(run_benchmark(iterations=args.iterations), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

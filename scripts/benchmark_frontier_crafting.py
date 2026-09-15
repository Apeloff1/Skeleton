#!/usr/bin/env python3
"""Observational benchmark for promoted frontier crafting policy.

Timing is evidence only. Correctness invariants are asserted while
machine-dependent latency thresholds remain excluded from CI.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from skeleton.frontier.crafting import (
    WorkshopState,
    collect_craft,
    recipe_from_record,
    start_craft,
)
from skeleton.frontier.crafting_adapters import energy_booster_from_craft_output


SOURCE_SEMANTICS = {
    "primary_repository": "Apeloff1/Lorebuffa",
    "primary_path": "backend/crafting_routes.py",
    "primary_blob": "9a9b159588605b8658b8d6043f62622c401dd8ba",
    "equivalent_repository": "Apeloff1/Openworld",
    "equivalent_path": "backend/crafting_routes.py",
    "equivalent_blob": "9a9b159588605b8658b8d6043f62622c401dd8ba",
}


def _recipe():
    return recipe_from_record(
        {
            "id": "energy_drink",
            "name": "Energy Drink",
            "category": "consumable",
            "ingredients": [
                {"item": "fresh_water", "quantity": 2},
                {"item": "sugar", "quantity": 1},
                {"item": "caffeine_berry", "quantity": 1},
            ],
            "output": {
                "item": "energy_drink",
                "quantity": 2,
                "effect": {"energy_restore": 25},
            },
            "craft_time_seconds": 45,
            "xp_reward": 10,
            "unlock_level": 2,
        }
    )


def run_benchmark(*, iterations: int = 2000) -> dict[str, Any]:
    if iterations < 1:
        raise ValueError("iterations must be positive")

    recipe = _recipe()
    booster = energy_booster_from_craft_output(recipe)
    workshop = WorkshopState(unlocked_recipes=frozenset({recipe.id}))
    materials = {
        "fresh_water": iterations * 2,
        "sugar": iterations,
        "caffeine_berry": iterations,
    }
    now = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)

    started = time.perf_counter_ns()
    outputs = 0
    for index in range(iterations):
        tick = now + timedelta(minutes=index)
        plan = start_craft(
            workshop,
            recipe,
            materials,
            slot=0,
            user_level=1,
            now=tick,
        )
        materials = dict(plan.materials)
        collected = collect_craft(
            plan.workshop,
            slot=0,
            now=plan.job.complete_at,
        )
        workshop = collected.workshop
        outputs += collected.output.quantity
    elapsed_ns = time.perf_counter_ns() - started

    expected_outputs = iterations * recipe.output.quantity
    if outputs != expected_outputs:
        raise AssertionError("craft output accounting mismatch")
    if workshop.total_crafted != iterations:
        raise AssertionError("total_crafted invariant violated")
    if any(materials.values()):
        raise AssertionError("material accounting invariant violated")
    if booster.energy_restore != 25:
        raise AssertionError("crafting-to-energy adapter invariant violated")

    elapsed_seconds = elapsed_ns / 1_000_000_000
    return {
        "workload": "frontier-crafting-policy-v1",
        "source_semantics": SOURCE_SEMANTICS,
        "configuration": {"iterations": iterations},
        "evidence": {
            "total_crafted": workshop.total_crafted,
            "output_items": outputs,
            "crafting_level": workshop.crafting_level,
            "crafting_xp": workshop.crafting_xp,
            "energy_restore_per_item": booster.energy_restore,
            "materials_exhausted_exactly": True,
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

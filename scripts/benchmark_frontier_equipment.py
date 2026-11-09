#!/usr/bin/env python3
"""Observational benchmark for promoted frontier equipment policy."""

from __future__ import annotations

import argparse
import json
import time
from typing import Any

from skeleton.frontier.equipment import (
    EquipmentLoadout,
    apply_equipment_purchase,
    calculate_equipment_bonuses,
    equip_item,
    equipment_from_record,
    quote_equipment_purchase,
)


SOURCE_SEMANTICS = {
    "primary_repository": "Apeloff1/Lorebuffa",
    "primary_path": "backend/equipment_routes.py",
    "primary_blob": "037724170943e13e237336f0df4631e2a81dd9d3",
    "equivalent_repository": "Apeloff1/Openworld",
    "equivalent_path": "backend/equipment_routes.py",
    "equivalent_blob": "037724170943e13e237336f0df4631e2a81dd9d3",
}


def _item(item_id: str, category: str, bonuses: dict[str, float]):
    return equipment_from_record(
        {
            "id": item_id,
            "name": item_id.replace("_", " ").title(),
            "category": category,
            "biotope": "saltwater",
            "stats": {"power": 60},
            "bonuses": bonuses,
            "cost": {"coins": 100},
            "unlock_level": 1,
            "rarity": "uncommon",
        }
    )


def run_benchmark(*, iterations: int = 5000) -> dict[str, Any]:
    if iterations < 1:
        raise ValueError("iterations must be positive")

    rod = _item(
        "surf_rod",
        "rod",
        {
            "saltwater_catch_rate": 1.15,
            "rare_fish_chance": 1.1,
            "saltwater_distance": 1.2,
        },
    )
    line = _item(
        "braid_line",
        "line",
        {"stealth_bonus": 1.05, "sensitivity_bonus": 1.2},
    )
    bobber = _item(
        "glow_bobber",
        "bobber",
        {"bite_detection": 1.3, "night_bonus": 1.1},
    )

    started = time.perf_counter_ns()
    checksum = 0.0
    for _ in range(iterations):
        loadout = EquipmentLoadout()
        for item in (rod, line, bobber):
            quote = quote_equipment_purchase(
                item,
                loadout,
                {"coins": 1000},
                user_level=10,
            )
            if not quote.can_purchase:
                raise AssertionError("equipment purchase quote unexpectedly blocked")
            loadout = apply_equipment_purchase(loadout, item)
            loadout = equip_item(loadout, item)
        bonuses = calculate_equipment_bonuses(
            rod,
            line,
            bobber,
            biotope="saltwater",
        )
        checksum += bonuses.catch_rate + bonuses.sensitivity
    elapsed_ns = time.perf_counter_ns() - started

    if loadout.equipped_rod != rod.id:
        raise AssertionError("rod equip invariant violated")
    if loadout.equipped_line != line.id:
        raise AssertionError("line equip invariant violated")
    if loadout.equipped_bobber != bobber.id:
        raise AssertionError("bobber equip invariant violated")
    if checksum <= 0:
        raise AssertionError("equipment benchmark checksum must be positive")

    elapsed_seconds = elapsed_ns / 1_000_000_000
    return {
        "workload": "frontier-equipment-policy-v1",
        "source_semantics": SOURCE_SEMANTICS,
        "configuration": {"iterations": iterations},
        "evidence": {
            "checksum": checksum,
            "equipped": {
                "rod": loadout.equipped_rod,
                "line": loadout.equipped_line,
                "bobber": loadout.equipped_bobber,
            },
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
    parser.add_argument("--iterations", type=int, default=5000)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    print(json.dumps(run_benchmark(iterations=args.iterations), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

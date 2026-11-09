#!/usr/bin/env python3
"""Observational benchmark for promoted bait/fishing-spot policy."""

from __future__ import annotations

import argparse
import json
import time
from typing import Any

from skeleton.frontier.bait import (
    BaitLoadout,
    bait_from_record,
    bait_purchase_cost,
    calculate_catch_bonuses,
    equip_bait,
    spot_from_record,
    use_bait,
)


SOURCE_SEMANTICS = {
    "primary_repository": "Apeloff1/Lorebuffa",
    "primary_path": "backend/bait_routes.py",
    "primary_blob": "9963db63e814d84b6292ecc0cc4fe3c2b2b077e8",
    "equivalent_repository": "Apeloff1/Openworld",
    "equivalent_path": "backend/bait_routes.py",
    "equivalent_blob": "9963db63e814d84b6292ecc0cc4fe3c2b2b077e8",
}


def run_benchmark(*, iterations: int = 5000) -> dict[str, Any]:
    if iterations < 1:
        raise ValueError("iterations must be positive")

    bait = bait_from_record(
        {
            "id": "storm_bait",
            "name": "Storm Bait",
            "rarity": "rare",
            "durability": 4,
            "cost": {"coins": 80},
            "catch_bonus": 1.4,
            "rare_bonus": 1.5,
            "storm_bonus": 2.0,
            "effective_fish": ["storm_fish", "catfish"],
        }
    )
    spot = spot_from_record(
        {
            "id": "ocean",
            "name": "Deep Ocean",
            "difficulty": 4,
            "unlock_level": 25,
            "bonuses": {"xp": 1.8, "coins": 1.5, "rare_chance": 1.3},
            "requires_boat": True,
        }
    )

    started = time.perf_counter_ns()
    checksum = 0.0
    uses = 0
    for index in range(iterations):
        purchase = bait_purchase_cost(bait, (index % 3) + 1)
        loadout = equip_bait(BaitLoadout(), bait, owned_quantity=1).next_loadout
        while loadout.equipped_bait is not None:
            use = use_bait(loadout, bait)
            loadout = use.next_loadout
            uses += int(use.bait_used)
        bonuses = calculate_catch_bonuses(
            bait,
            spot,
            is_night=index % 2 == 0,
            is_storm=True,
        )
        checksum += bonuses.catch_rate + bonuses.rare_chance + purchase["coins"]

    elapsed_ns = time.perf_counter_ns() - started
    if uses != iterations * bait.durability:
        raise AssertionError("bait durability accounting mismatch")
    if checksum <= 0:
        raise AssertionError("benchmark checksum must be positive")

    elapsed_seconds = elapsed_ns / 1_000_000_000
    return {
        "workload": "frontier-bait-policy-v1",
        "source_semantics": SOURCE_SEMANTICS,
        "configuration": {"iterations": iterations},
        "evidence": {
            "uses": uses,
            "checksum": checksum,
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

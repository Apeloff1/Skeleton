#!/usr/bin/env python3
"""Observational benchmark for biotope-to-achievement adapters."""

from __future__ import annotations

import argparse
import json
import time
from typing import Any

from skeleton.frontier.achievements import AchievementState, qualifies
from skeleton.frontier.biotope import BiotopeProgress
from skeleton.frontier.biotope_achievement_adapters import (
    biotope_achievement_from_record,
    record_biotope_achievement_catch,
    requirement_signals_for_achievement,
)

SOURCE_SEMANTICS = {
    "repository_a": "Apeloff1/Lorebuffa",
    "repository_b": "Apeloff1/Openworld",
    "path": "backend/biotope_achievements_routes.py",
    "shared_blob": "5a06312eebf8bb21fef28b1010dfc3ccff6b6500",
    "equivalence": "byte-identical source; definitions/signals adapted once",
}


def _world_angler():
    return biotope_achievement_from_record(
        {
            "id": "world_angler",
            "name": "World Angler",
            "biotope": "all",
            "category": "exploration",
            "requirement": {
                "type": "biotopes_mastered",
                "count": 4,
                "each": 100,
            },
            "rewards": {
                "xp": 5000,
                "coins": 25000,
                "gems": 250,
                "title": "World Angler",
            },
        }
    )


def _mastered_progress() -> BiotopeProgress:
    biotopes = frozenset(
        {"freshwater_lake", "saltwater", "brackish", "river"}
    )
    return BiotopeProgress(
        unlocked_biotopes=biotopes,
        unlocked_stages=frozenset({"pond"}),
        current_biotope="freshwater_lake",
        current_stage="pond",
        biotope_xp={key: 0 for key in biotopes},
        biotope_level={key: 1 for key in biotopes},
        fish_caught_by_biotope={key: 100 for key in biotopes},
    )


def run_benchmark(*, iterations: int = 2000) -> dict[str, Any]:
    if isinstance(iterations, bool) or not isinstance(iterations, int):
        raise TypeError("iterations must be an integer")
    if iterations < 1:
        raise ValueError("iterations must be positive")

    world_angler = _world_angler()
    progress = _mastered_progress()
    signals = requirement_signals_for_achievement(world_angler, progress)
    if not qualifies(world_angler, AchievementState(), signals=signals):
        raise AssertionError("world angler each-threshold semantics failed")

    started = time.perf_counter_ns()
    qualified = 0
    lake_alias_updates = 0
    trophy_max = 0
    for _ in range(iterations):
        state = record_biotope_achievement_catch(
            AchievementState(),
            biotope_id="freshwater_lake",
            stage_id="deep_lake",
            rarity="rare",
            size_cm=120,
            species_groups=("bass",),
        )
        if state.stats.get("lake_catches") != 1:
            raise AssertionError("freshwater lake alias normalization failed")
        if "freshwater_lake_catches" in state.stats:
            raise AssertionError("source-incompatible lake stat leaked")
        if state.stats.get("bass_catches") != 1:
            raise AssertionError("explicit species signal failed")
        if state.stats.get("lake_trophy") != 120:
            raise AssertionError("trophy max-stat projection failed")
        lake_alias_updates += 1
        trophy_max += state.stats["lake_trophy"]

        derived = requirement_signals_for_achievement(world_angler, progress)
        qualified += int(
            qualifies(world_angler, AchievementState(), signals=derived)
        )

    elapsed_ns = time.perf_counter_ns() - started
    if qualified != iterations:
        raise AssertionError("cross-biotope qualification accounting mismatch")
    if lake_alias_updates != iterations:
        raise AssertionError("lake alias accounting mismatch")
    if trophy_max != iterations * 120:
        raise AssertionError("trophy accounting mismatch")

    elapsed_seconds = elapsed_ns / 1_000_000_000
    return {
        "workload": "frontier-biotope-achievement-adapters-v1",
        "source_semantics": SOURCE_SEMANTICS,
        "configuration": {"iterations": iterations},
        "evidence": {
            "qualified": qualified,
            "lake_alias_updates": lake_alias_updates,
            "trophy_max_sum": trophy_max,
            "world_angler_each_rule_holds": True,
            "explicit_species_signals": True,
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

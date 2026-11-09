#!/usr/bin/env python3
"""Observational benchmark for promoted biotope progression policy."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import time
from typing import Any

from skeleton.frontier.biotope import (
    BiotopeSpec,
    BiotopeStageSpec,
    calculate_biotope_bonus,
    initial_progress,
    record_catch,
    unlock_biotope,
    unlock_stage,
    unlockable_biotopes,
)
from skeleton.frontier.biotope_adapters import (
    biotope_event,
    biotope_event_to_memory_item,
    biotope_progress_digest,
)

SOURCE_SEMANTICS = {
    "repository_a": "Apeloff1/Lorebuffa",
    "repository_b": "Apeloff1/Openworld",
    "path": "backend/biotope_routes.py",
    "shared_blob": "b79a167a3b568477e7db1fa95d64fc3949171a7e",
    "equivalence": "byte-identical source implementation; portable policy promoted once",
}
NOW = datetime(2026, 9, 15, 13, 15, tzinfo=timezone.utc)


def _lake_stages() -> tuple[BiotopeStageSpec, ...]:
    return (
        BiotopeStageSpec("pond", "freshwater_lake", 1, 1),
        BiotopeStageSpec("shallow_lake", "freshwater_lake", 2, 10),
        BiotopeStageSpec("deep_lake", "freshwater_lake", 3, 25),
    )


def _salt_stages() -> tuple[BiotopeStageSpec, ...]:
    return (
        BiotopeStageSpec("coastal_shallows", "saltwater", 1, 15),
        BiotopeStageSpec("coral_reef", "saltwater", 2, 25),
    )


def run_benchmark(*, iterations: int = 2000) -> dict[str, Any]:
    if isinstance(iterations, bool) or not isinstance(iterations, int):
        raise TypeError("iterations must be an integer")
    if iterations < 1:
        raise ValueError("iterations must be positive")

    lake_stages = _lake_stages()
    saltwater = BiotopeSpec("saltwater", 15, required_boat=True)
    river = BiotopeSpec("river", 8)
    brackish = BiotopeSpec("brackish", 25)

    unlockable = unlockable_biotopes(
        initial_progress(),
        (brackish, saltwater, river),
        player_level=20,
        has_boat=False,
    )
    if tuple(spec.id for spec in unlockable) != ("river",):
        raise AssertionError("biotope unlock ordering or boat gating drifted")

    staged = unlock_stage(
        initial_progress(),
        lake_stages[1],
        stages=lake_stages,
        player_level=10,
    )
    if "shallow_lake" not in staged.unlocked_stages:
        raise AssertionError("sequential stage unlock failed")

    salt_progress = unlock_biotope(
        initial_progress(),
        saltwater,
        stages=_salt_stages(),
        player_level=15,
        has_boat=True,
    )
    if "coastal_shallows" not in salt_progress.unlocked_stages:
        raise AssertionError("biotope unlock did not seed stage one")

    started = time.perf_counter_ns()
    projections = 0
    mastery_levels = 0
    unique_digests: set[str] = set()
    for index in range(iterations):
        plan = record_catch(
            initial_progress(),
            "freshwater_lake",
            xp_earned=650,
        )
        if plan.levels_gained != 3:
            raise AssertionError("mastery rollover accounting mismatch")
        if plan.progress.biotope_level["freshwater_lake"] != 4:
            raise AssertionError("mastery level mismatch")
        if plan.progress.biotope_xp["freshwater_lake"] != 50:
            raise AssertionError("mastery XP residue mismatch")
        if plan.bonus != calculate_biotope_bonus(4):
            raise AssertionError("mastery bonus mismatch")

        digest = biotope_progress_digest(plan.progress)
        unique_digests.add(digest)
        event = biotope_event(
            plan.progress,
            subject_id=f"player-{index}",
            action="catch_recorded",
            occurred_at=NOW,
        )
        memory = biotope_event_to_memory_item(event)
        if memory["metadata"]["total_catches"] != 1:
            raise AssertionError("biotope memory catch count mismatch")
        if memory["metadata"]["highest_mastery_level"] != 4:
            raise AssertionError("biotope memory mastery mismatch")
        projections += 1
        mastery_levels += plan.progress.biotope_level["freshwater_lake"]

    elapsed_ns = time.perf_counter_ns() - started
    if projections != iterations:
        raise AssertionError("biotope projection accounting mismatch")
    if mastery_levels != iterations * 4:
        raise AssertionError("biotope mastery accounting mismatch")
    if len(unique_digests) != 1:
        raise AssertionError("equivalent biotope states produced unstable digests")

    elapsed_seconds = elapsed_ns / 1_000_000_000
    return {
        "workload": "frontier-biotope-policy-v1",
        "source_semantics": SOURCE_SEMANTICS,
        "configuration": {"iterations": iterations},
        "evidence": {
            "memory_projections": projections,
            "mastery_level_sum": mastery_levels,
            "stable_state_digests": len(unique_digests),
            "boat_gate_holds": True,
            "sequential_stage_gate_holds": True,
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

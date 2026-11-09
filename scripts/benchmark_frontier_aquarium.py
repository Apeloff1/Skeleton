#!/usr/bin/env python3
"""Observational benchmark for the canonical promoted aquarium policy."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import time
from typing import Any

from skeleton.frontier.aquarium import (
    AquariumDecorationSpec,
    AquariumPosition,
    AquariumTankSpec,
    DisplayFish,
    add_fish,
    initial_aquarium,
    place_decoration,
    purchase_decoration,
)
from skeleton.frontier.aquarium_adapters import (
    aquarium_event,
    aquarium_event_to_memory_item,
    aquarium_state_digest,
)

SOURCE_SEMANTICS = {
    "repository_a": "Apeloff1/Lorebuffa",
    "repository_b": "Apeloff1/Openworld",
    "path": "backend/aquarium_routes.py",
    "shared_blob": "223f65a8b8cb4c60528e6c4cc585a01296178ea0",
    "equivalence": "byte-identical source implementation; portable policy promoted once",
}
NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)


def _starter() -> AquariumTankSpec:
    return AquariumTankSpec("starter", "Starter", 10, 100, 50, 3)


def _fish(identity: str) -> DisplayFish:
    return DisplayFish(
        identity,
        "Blue Fish",
        "blue_fish",
        20,
        "#4A90D9",
        {},
        AquariumPosition(50, 50),
        NOW,
    )


def run_benchmark(*, iterations: int = 2000) -> dict[str, Any]:
    if isinstance(iterations, bool) or not isinstance(iterations, int):
        raise TypeError("iterations must be an integer")
    if iterations < 1:
        raise ValueError("iterations must be positive")

    starter = _starter()
    seaweed = AquariumDecorationSpec(
        "seaweed", "Seaweed", "plant", {"coins": 100}, icon="plant"
    )

    duplicate_rejected = False
    once = add_fish(initial_aquarium(), starter, _fish("same-fish")).aquarium
    try:
        add_fish(once, starter, _fish("same-fish"))
    except ValueError as exc:
        duplicate_rejected = "already displayed" in str(exc)
    if not duplicate_rejected:
        raise AssertionError("duplicate aquarium fish identity was not rejected")

    started = time.perf_counter_ns()
    projected = 0
    placed = 0
    unique_digests: set[str] = set()
    for index in range(iterations):
        purchase = purchase_decoration(
            initial_aquarium(), seaweed, balances={"coins": 200}, quantity=2
        )
        placement = place_decoration(
            purchase.aquarium,
            starter,
            seaweed,
            placement_id=f"placed-{index}",
            position=AquariumPosition(10, 20),
            placed_at=NOW,
        )
        if placement.aquarium.owned_decorations.get("seaweed") != 1:
            raise AssertionError("placing one decoration did not consume exactly one copy")

        state = add_fish(
            placement.aquarium, starter, _fish(f"fish-{index}")
        ).aquarium
        if state.total_fish_displayed != 1 or state.total_decorations_placed != 1:
            raise AssertionError("derived aquarium counts are inconsistent")

        unique_digests.add(aquarium_state_digest(state))
        memory = aquarium_event_to_memory_item(
            aquarium_event(
                state,
                subject_id=f"player-{index}",
                action="fish_added",
                occurred_at=NOW,
            )
        )
        if memory["metadata"]["fish_count"] != 1:
            raise AssertionError("aquarium memory fish count mismatch")
        if memory["metadata"]["decoration_count"] != 1:
            raise AssertionError("aquarium memory decoration count mismatch")
        projected += 1
        placed += 1

    elapsed_ns = time.perf_counter_ns() - started
    if projected != iterations or placed != iterations:
        raise AssertionError("aquarium benchmark accounting mismatch")
    if len(unique_digests) != iterations:
        raise AssertionError("aquarium state digests unexpectedly collided")

    elapsed_seconds = elapsed_ns / 1_000_000_000
    return {
        "workload": "frontier-aquarium-policy-v2",
        "source_semantics": SOURCE_SEMANTICS,
        "configuration": {"iterations": iterations},
        "evidence": {
            "duplicate_rejected": duplicate_rejected,
            "memory_projections": projected,
            "decorations_placed": placed,
            "unique_state_digests": len(unique_digests),
            "invariants_hold": True,
        },
        "timing": {
            "elapsed_seconds": elapsed_seconds,
            "iterations_per_second": iterations / elapsed_seconds if elapsed_seconds else None,
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

#!/usr/bin/env python3
"""Observational benchmark for promoted aquarium/display policy."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import time
from typing import Any

from skeleton.frontier.aquarium import add_fish, initial_aquarium, purchase_decoration, place_decoration
from skeleton.frontier.aquarium_adapters import aquarium_event, aquarium_event_to_memory_item, aquarium_state_digest
from skeleton.frontier.aquarium_models import AquariumPosition, AquariumTankSpec, DecorationSpec, DisplayFish


SOURCE_SEMANTICS = {
    "repository_a": "Apeloff1/Lorebuffa",
    "repository_b": "Apeloff1/Openworld",
    "path": "backend/aquarium_routes.py",
    "shared_blob": "223f65a8b8cb4c60528e6c4cc585a01296178ea0",
    "equivalence": "byte-identical source implementation; portable policy promoted once",
}


def run_benchmark(*, iterations: int = 2000) -> dict[str, Any]:
    if isinstance(iterations, bool) or not isinstance(iterations, int):
        raise TypeError("iterations must be an integer")
    if iterations < 1:
        raise ValueError("iterations must be positive")

    starter = AquariumTankSpec("starter", "Starter", 10, 1, 3)
    seaweed = DecorationSpec("seaweed", "Seaweed", "plant", {"coins": 100})
    now = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)

    duplicate_rejected = False
    once = add_fish(
        initial_aquarium(),
        starter,
        DisplayFish("same", "Blue Fish", "blue_fish", 20, AquariumPosition(50, 50)),
    ).aquarium
    try:
        add_fish(
            once,
            starter,
            DisplayFish("same", "Blue Fish", "blue_fish", 20, AquariumPosition(50, 50)),
        )
    except ValueError as exc:
        duplicate_rejected = "already displayed" in str(exc)
    if not duplicate_rejected:
        raise AssertionError("duplicate fish identity was not rejected")

    started = time.perf_counter_ns()
    digest_set: set[str] = set()
    memory_count = 0
    decoration_count = 0
    for index in range(iterations):
        state = initial_aquarium()
        state = purchase_decoration(state, seaweed, quantity=2)
        placed = place_decoration(
            state,
            starter,
            seaweed,
            position=AquariumPosition(10, 20),
            now=now,
            identity=lambda index=index: f"placed-{index}",
        )
        if placed.aquarium.owned_decorations["seaweed"] != 1:
            raise AssertionError("decoration placement did not consume exactly one item")
        fish = DisplayFish(
            f"fish-{index}",
            "Blue Fish",
            "blue_fish",
            20,
            AquariumPosition(50, 50),
            added_at=now,
        )
        state = add_fish(placed.aquarium, starter, fish).aquarium
        digest = aquarium_state_digest(state)
        digest_set.add(digest)
        event = aquarium_event(
            state,
            subject_id=f"player-{index}",
            action="fish_added",
            occurred_at=now,
        )
        memory = aquarium_event_to_memory_item(event)
        if memory["metadata"]["fish_count"] != 1:
            raise AssertionError("aquarium memory fish count mismatch")
        if memory["metadata"]["decoration_count"] != 1:
            raise AssertionError("aquarium memory decoration count mismatch")
        memory_count += 1
        decoration_count += len(state.tanks["starter"].decorations)

    elapsed_ns = time.perf_counter_ns() - started
    if memory_count != iterations:
        raise AssertionError("aquarium memory projection count mismatch")
    if decoration_count != iterations:
        raise AssertionError("aquarium decoration accounting mismatch")
    if len(digest_set) != iterations:
        raise AssertionError("aquarium state digests unexpectedly collided")

    elapsed_seconds = elapsed_ns / 1_000_000_000
    return {
        "workload": "frontier-aquarium-policy-v1",
        "source_semantics": SOURCE_SEMANTICS,
        "configuration": {"iterations": iterations},
        "evidence": {
            "duplicate_rejected": duplicate_rejected,
            "memory_projections": memory_count,
            "decorations_placed": decoration_count,
            "unique_state_digests": len(digest_set),
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

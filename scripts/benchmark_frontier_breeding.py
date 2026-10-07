#!/usr/bin/env python3
"""Observational benchmark for promoted frontier breeding policy.

Timing is evidence only. Correctness assertions are part of the workload;
machine-dependent latency thresholds are deliberately excluded.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from typing import Any, Sequence

from skeleton.frontier.breeding import (
    BreedingParent,
    BreedingProgress,
    FishSpeciesSpec,
    SpecialBreedSpec,
    apply_breeding_reward,
    offspring_plan,
    refresh_breeding,
    start_breeding,
)
from skeleton.frontier.breeding_adapters import (
    breeding_event_to_memory_item,
    breeding_offspring_event,
)


SOURCE_SEMANTICS = {
    "primary_repository": "Apeloff1/Lorebuffa",
    "primary_path": "backend/breeding_routes.py",
    "primary_blob": "8f016084c60b44a4d3d09d16f6e5076722355212",
    "equivalent_repository": "Apeloff1/Openworld",
    "equivalent_path": "backend/breeding_routes.py",
    "equivalent_blob": "8f016084c60b44a4d3d09d16f6e5076722355212",
}


class _DeterministicRng:
    def __init__(self) -> None:
        self.counter = 0

    def random(self) -> float:
        self.counter += 1
        return 0.01 if self.counter % 29 == 0 else 0.9

    def choice(self, values: Sequence[str]) -> str:
        self.counter += 1
        return values[self.counter % len(values)]

    def uniform(self, lower: float, upper: float) -> float:
        self.counter += 1
        return (lower + upper) / 2.0


def run_benchmark(*, iterations: int = 2500) -> dict[str, Any]:
    if iterations < 1:
        raise ValueError("iterations must be positive")

    now = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
    species = {
        "bass": FishSpeciesSpec("bass", 40, 3, ("koi",)),
        "koi": FishSpeciesSpec("koi", 200, 8, ("bass",)),
    }
    special = SpecialBreedSpec(
        id="rainbow_bass",
        name="Rainbow Bass",
        parents=("bass", "koi"),
        required_traits={"color": "rainbow"},
        rarity="rare",
        base_value=300,
    )
    trait_domains = {
        "color": ("red", "blue", "rainbow"),
        "pattern": ("solid", "iridescent"),
        "size_gene": ("medium", "large"),
        "rarity_gene": ("common", "rare"),
    }
    parent1 = BreedingParent(
        "p1",
        "bass",
        {
            "color": "red",
            "pattern": "solid",
            "size_gene": "medium",
            "rarity_gene": "common",
        },
        50,
    )
    parent2 = BreedingParent(
        "p2",
        "koi",
        {
            "color": "blue",
            "pattern": "iridescent",
            "size_gene": "large",
            "rarity_gene": "rare",
        },
        70,
    )
    rng = _DeterministicRng()
    progress = BreedingProgress()

    started = time.perf_counter_ns()
    checksum = 0
    special_count = 0
    for index in range(iterations):
        job = start_breeding(
            parent1,
            parent2,
            parent1_slot=0,
            parent2_slot=1,
            species=species,
            now=now,
        )
        job = refresh_breeding(job, job.complete_at)
        if job.status != "complete":
            raise AssertionError("breeding job did not complete")

        plan = offspring_plan(
            job,
            trait_domains=trait_domains,
            species=species,
            specials=(special,),
            known_discoveries=progress.rare_discoveries,
            rng=rng,
            id_factory=lambda index=index: f"offspring-{index}",
            now=job.complete_at,
        )
        progress = apply_breeding_reward(
            progress,
            special_breed=special if plan.special_breed_id else None,
        )
        event = breeding_offspring_event(
            plan,
            subject_id="benchmark-subject",
            occurred_at=plan.bred_at,
        )
        item = breeding_event_to_memory_item(event)
        checksum += int(item["metadata"]["value"])
        special_count += int(plan.special_breed_id is not None)

    elapsed_ns = time.perf_counter_ns() - started
    if progress.total_bred != iterations:
        raise AssertionError("breeding progress count mismatch")
    if checksum <= 0:
        raise AssertionError("benchmark checksum must be positive")

    elapsed_seconds = elapsed_ns / 1_000_000_000
    return {
        "workload": "frontier-breeding-policy-v1",
        "source_semantics": SOURCE_SEMANTICS,
        "configuration": {"iterations": iterations},
        "evidence": {
            "total_bred": progress.total_bred,
            "breeding_level": progress.level,
            "special_count": special_count,
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
    parser.add_argument("--iterations", type=int, default=2500)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    print(json.dumps(run_benchmark(iterations=args.iterations), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

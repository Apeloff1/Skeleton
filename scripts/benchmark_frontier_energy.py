#!/usr/bin/env python3
"""Observational benchmark for promoted frontier energy policy.

Timing is evidence only. Correctness assertions are part of the workload;
machine-dependent latency thresholds are deliberately excluded.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from skeleton.frontier.energy import (
    EnergyBoosterSpec,
    EnergyState,
    apply_booster,
    consume_energy,
    regenerate_energy,
    restore_energy,
)
from skeleton.frontier.energy_adapters import (
    energy_event,
    energy_event_to_memory_item,
)


SOURCE_SEMANTICS = {
    "primary_repository": "Apeloff1/Lorebuffa",
    "primary_path": "backend/energy_routes.py",
    "primary_blob": "cac117f5de074756bdea557b8f419714fb215621",
    "compared_repository": "Apeloff1/Openworld",
    "compared_path": "backend/energy_routes.py",
    "compared_blob": "cd6fd76d71e3a9b3e4e5abf5cc0fc1e5cf584788",
}


def run_benchmark(*, iterations: int = 5000) -> dict[str, Any]:
    if iterations < 1:
        raise ValueError("iterations must be positive")

    now = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
    booster = EnergyBoosterSpec(
        id="double_regen_30m",
        name="Double Regen",
        regen_multiplier=2.0,
        duration_minutes=30,
    )
    state = EnergyState(
        current_energy=50,
        max_energy=100,
        last_updated=now,
    )

    started = time.perf_counter_ns()
    checksum = 0
    for index in range(iterations):
        tick = now + timedelta(minutes=index + 1)
        state = regenerate_energy(state, now=tick)
        if state.current_energy >= 95:
            state = consume_energy(state, 25, now=tick)
        if index % 17 == 0:
            state = restore_energy(state, 3, now=tick)
        if index % 101 == 0:
            state = apply_booster(state, booster, now=tick)
        event = energy_event(
            state,
            subject_id="benchmark-subject",
            action="synchronized",
            occurred_at=tick,
        )
        item = energy_event_to_memory_item(event)
        checksum += int(item["metadata"]["current_energy"])
    elapsed_ns = time.perf_counter_ns() - started

    if not (0 <= state.current_energy <= state.max_energy):
        raise AssertionError("energy invariant violated")
    if checksum <= 0:
        raise AssertionError("benchmark checksum must be positive")

    elapsed_seconds = elapsed_ns / 1_000_000_000
    return {
        "workload": "frontier-energy-policy-v1",
        "source_semantics": SOURCE_SEMANTICS,
        "configuration": {"iterations": iterations},
        "evidence": {
            "final_current_energy": state.current_energy,
            "final_max_energy": state.max_energy,
            "total_energy_spent": state.total_energy_spent,
            "total_energy_restored": state.total_energy_restored,
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

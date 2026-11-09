"""Actual consumer-machine cost lab for era NPC population fidelity.

No benchmark times or memory metrics are asserted in documentation. They are
recorded only from code really executed on the host. CPU timings are noisy,
not deterministic world state, and are not part of save/replay or game logic.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from time import perf_counter_ns
import tracemalloc

from .original_foundation_compiler import FoundationError
from .original_world_era_runtime import ERA_LEVELS
from .original_world_living_10x_compiler import living_for
from .original_world_product_session import (
    ProductAction, create_product, product_save, step_product,
)
from .original_world_npc_era_population import (
    FIDELITY_MODES, active_brain_budget, population_report,
)

BENCH_SCHEMA = "original-world-era-npc-cost-measurement.v1"


def benchmark_era(
    era: str, preset: str = "balanced", *,
    turns: int = 3, trace_allocations: bool = False,
) -> dict:
    if era not in ERA_LEVELS or preset not in FIDELITY_MODES:
        raise FoundationError("unknown era or fidelity workload")
    if type(turns) is not int or not 1 <= turns <= 16:
        raise FoundationError("finite CPU benchmark requires 1..16 world turns")
    design = living_for(0, "puzzle", "lattice", "trophic", "sandbox")
    state = create_product(design.index, era=era, npc_fidelity=preset)
    inhabitants = len(state.society.inhabitants)
    decisions_before = sum(m.decisions for m in state.cognition.minds)
    population_before = sum(d.population for d in state.population.districts)
    receipts = []
    if trace_allocations:
        tracemalloc.start()
    start = perf_counter_ns()
    try:
        for _ in range(turns):
            state, receipt = step_product(state, ProductAction("causal", "end_turn"))
            receipts.append(receipt.receipt)
        elapsed = perf_counter_ns() - start
        peak = tracemalloc.get_traced_memory()[1] if trace_allocations else None
    finally:
        if trace_allocations:
            tracemalloc.stop()
    decisions = sum(m.decisions for m in state.cognition.minds) - decisions_before
    report = population_report(state.population, inhabitants)
    return {
        "schema": BENCH_SCHEMA,
        "era": era,
        "preset": preset,
        "world_turns_actually_advanced": turns,
        "local_physically_simulated_NPCs": inhabitants,
        "local_cognitive_action_slots_used": decisions,
        "scheduled_max_per_turn": min(
            inhabitants, active_brain_budget(era, preset)),
        "local_brain_slots_saved_against_full_simulation":
            inhabitants * turns - decisions,
        "regional_census_before": population_before,
        "regional_census_after": report["regional_aggregated_residents"],
        "regional_districts": report["districts"],
        "regional_updates": state.population.updates,
        "actual_wall_time_ns": elapsed,
        "actual_mean_ns_per_world_turn": elapsed // turns,
        "optional_peak_python_allocated_bytes": peak,
        "final_real_save_sha256": sha256(product_save(state).encode()).hexdigest(),
        "first_event_receipt": receipts[0],
        "last_event_receipt": receipts[-1],
        "measurement_limits": (
            "Wall-clock cost and traced Python allocations are environment-"
            "dependent; measured local hardware, not a scientific CPU or "
            "GPU benchmark, and no implied guarantee on other devices."
        ),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure actual original-era NPC cognition and regional cost"
    )
    parser.add_argument("--era", choices=tuple(ERA_LEVELS), default="digital-network")
    parser.add_argument("--preset", choices=FIDELITY_MODES, default="balanced")
    parser.add_argument("--turns", type=int, default=3)
    parser.add_argument("--trace-memory", action="store_true")
    args = parser.parse_args(argv)
    try:
        data = benchmark_era(args.era, args.preset, turns=args.turns,
                             trace_allocations=args.trace_memory)
    except (FoundationError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(data, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

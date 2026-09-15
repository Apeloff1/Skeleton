#!/usr/bin/env python3
"""Benchmark promoted achievement policy without turning timing into a CI gate.

The workload characterizes pure normalization, stat progression, qualification,
event projection and memory projection derived from the shared Lorebuffa /
Openworld achievement source. Results are evidence only; correctness assertions
belong in tests and no machine-dependent latency threshold is enforced.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from typing import Any

from skeleton.frontier.achievement_adapters import (
    achievement_event,
    achievement_event_to_memory_item,
)
from skeleton.frontier.achievements import (
    AchievementState,
    achievement_from_record,
    achievement_summary,
    unlock_qualified,
    update_stat,
)


SOURCE_BLOB = "c6410bfd3bbde13454b2641a7982838893d970d9"


def run_benchmark(*, achievements: int, transitions: int) -> dict[str, Any]:
    if achievements < 1 or transitions < 1:
        raise ValueError("achievements and transitions must be positive")

    normalize_started = time.perf_counter_ns()
    catalog = tuple(
        achievement_from_record(
            {
                "id": f"progress-{index + 1}",
                "name": f"Progress {index + 1}",
                "description": "Synthetic benchmark definition",
                "category": "progression",
                "xp_reward": index + 1,
                "hidden": False,
                "requirement": {
                    "type": "fish_caught",
                    "count": index + 1,
                },
            }
        )
        for index in range(achievements)
    )
    normalize_elapsed = time.perf_counter_ns() - normalize_started

    state = AchievementState()
    progress_started = time.perf_counter_ns()
    for _ in range(transitions):
        state = update_stat(state, "fish_caught", 1)
    progress_elapsed = time.perf_counter_ns() - progress_started

    unlock_started = time.perf_counter_ns()
    state, unlocked = unlock_qualified(catalog, state)
    unlock_elapsed = time.perf_counter_ns() - unlock_started

    occurred_at = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
    projection_started = time.perf_counter_ns()
    memory_items = tuple(
        achievement_event_to_memory_item(
            achievement_event(
                achievement,
                subject_id="benchmark-subject",
                action="unlocked",
                occurred_at=occurred_at,
            )
        )
        for achievement in unlocked
    )
    projection_elapsed = time.perf_counter_ns() - projection_started

    expected_unlocked = min(achievements, transitions)
    if len(unlocked) != expected_unlocked:
        raise AssertionError("achievement qualification count drifted")
    if len(memory_items) != expected_unlocked:
        raise AssertionError("achievement projection count drifted")
    if len({item["id"] for item in memory_items}) != expected_unlocked:
        raise AssertionError("achievement projection identities are not unique")

    summary = achievement_summary(catalog, state)
    return {
        "workload": "frontier-achievement-policy-v1",
        "source_semantics": {
            "repository": "Apeloff1/Lorebuffa",
            "path": "backend/achievement_routes.py",
            "blob": SOURCE_BLOB,
            "equivalent_repository": "Apeloff1/Openworld",
        },
        "configuration": {
            "achievements": achievements,
            "transitions": transitions,
        },
        "evidence": {
            "final_fish_caught": state.stats["fish_caught"],
            "unlocked": len(unlocked),
            "projected_memory_items": len(memory_items),
            "unique_memory_ids": len({item["id"] for item in memory_items}),
            "summary": dict(summary),
        },
        "timing": {
            "normalize_seconds": normalize_elapsed / 1_000_000_000,
            "progress_seconds": progress_elapsed / 1_000_000_000,
            "unlock_seconds": unlock_elapsed / 1_000_000_000,
            "projection_seconds": projection_elapsed / 1_000_000_000,
            "transition_ops_per_second": (
                transitions / (progress_elapsed / 1_000_000_000)
                if progress_elapsed
                else None
            ),
            "projection_ops_per_second": (
                len(memory_items) / (projection_elapsed / 1_000_000_000)
                if projection_elapsed and memory_items
                else None
            ),
        },
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--achievements", type=int, default=500)
    parser.add_argument("--transitions", type=int, default=1000)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    print(
        json.dumps(
            run_benchmark(
                achievements=args.achievements,
                transitions=args.transitions,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

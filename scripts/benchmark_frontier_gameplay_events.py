#!/usr/bin/env python3
"""Observational benchmark for limited-time gameplay-event policy."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import time
from typing import Any

from skeleton.frontier.gameplay_event_adapters import (
    gameplay_event_to_memory_item,
    gameplay_event_transition,
)
from skeleton.frontier.gameplay_events import (
    claim_event_milestone,
    event_spec_from_record,
    event_time_restriction_active,
    initial_event_progress,
    update_event_progress,
)

SOURCE_SEMANTICS = {
    "repository_a": "Apeloff1/Lorebuffa",
    "repository_b": "Apeloff1/Openworld",
    "path": "backend/event_routes.py",
    "shared_blob": "6e7d62f7c5310374a3dad9cfdf22c1c28efc0cba",
    "equivalence": "byte-identical source; gameplay policy promoted without duplicate EventBus",
}
NOW = datetime(2026, 9, 15, 20, 0, tzinfo=timezone.utc)


def _spec():
    return event_spec_from_record(
        {
            "id": "midnight_madness",
            "duration_days": 3,
            "time_restriction": {"start_hour": 20, "end_hour": 6},
            "multipliers": {"xp": 2.5, "coins": 2.0, "rare_chance": 2.0},
            "challenges": [
                {
                    "id": "night_catches",
                    "target": 10,
                    "reward": {"coins": 1000, "event_tokens": 25},
                }
            ],
            "rewards": {
                1000: {"coins": 1000, "event_tokens": 100},
                5000: {"gems": 25, "title": "Night Champion"},
            },
        }
    )


def run_benchmark(*, iterations: int = 2000) -> dict[str, Any]:
    if isinstance(iterations, bool) or not isinstance(iterations, int):
        raise TypeError("iterations must be an integer")
    if iterations < 1:
        raise ValueError("iterations must be positive")

    spec = _spec()
    if not event_time_restriction_active(spec.time_restriction, at=NOW):
        raise AssertionError("midnight event restriction should be active at 20:00 UTC")

    started = time.perf_counter_ns()
    projections = 0
    challenge_awards = 0
    milestone_token_sum = 0
    for index in range(iterations):
        progress = initial_event_progress(spec, joined_at=NOW)
        update = update_event_progress(
            progress,
            spec,
            points_earned=1200,
            fish_caught={"night_fish": 10},
            challenge_progress={"night_catches": 10},
        )
        if len(update.newly_completed) != 1:
            raise AssertionError("challenge completion accounting mismatch")
        if update.progress.event_tokens != 25:
            raise AssertionError("challenge event-token accounting mismatch")
        challenge_awards += len(update.newly_completed)

        repeated = update_event_progress(
            update.progress,
            spec,
            challenge_progress={"night_catches": 1},
        )
        if repeated.newly_completed:
            raise AssertionError("completed challenge rewarded more than once")

        claim = claim_event_milestone(
            repeated.progress,
            spec,
            milestone=1000,
        )
        if claim.progress.event_tokens != 125:
            raise AssertionError("milestone event-token accounting mismatch")
        milestone_token_sum += claim.event_tokens_awarded

        event = gameplay_event_transition(
            claim.progress,
            spec,
            subject_id=f"player-{index}",
            action="milestone_claimed",
            occurred_at=NOW,
        )
        memory = gameplay_event_to_memory_item(event)
        if memory["metadata"]["points"] != 1200:
            raise AssertionError("gameplay-event memory points mismatch")
        if memory["metadata"]["completed_challenge_count"] != 1:
            raise AssertionError("gameplay-event memory challenge mismatch")
        if memory["metadata"]["claimed_milestone_count"] != 1:
            raise AssertionError("gameplay-event memory milestone mismatch")
        projections += 1

    elapsed_ns = time.perf_counter_ns() - started
    if projections != iterations:
        raise AssertionError("gameplay-event memory projection mismatch")
    if challenge_awards != iterations:
        raise AssertionError("gameplay-event challenge award mismatch")
    if milestone_token_sum != iterations * 100:
        raise AssertionError("gameplay-event milestone token mismatch")

    elapsed_seconds = elapsed_ns / 1_000_000_000
    return {
        "workload": "frontier-gameplay-events-v1",
        "source_semantics": SOURCE_SEMANTICS,
        "configuration": {"iterations": iterations},
        "evidence": {
            "memory_projections": projections,
            "challenge_awards": challenge_awards,
            "milestone_token_sum": milestone_token_sum,
            "single_shot_challenge_rewards": True,
            "midnight_window_holds": True,
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

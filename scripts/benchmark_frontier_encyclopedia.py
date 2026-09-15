#!/usr/bin/env python3
"""Observational benchmark for promoted encyclopedia collection policy."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import time
from typing import Any

from skeleton.frontier.encyclopedia import (
    collection_completion_percent,
    collection_summary,
    empty_collection,
    project_fish_entry,
    record_fish_catch,
)
from skeleton.frontier.encyclopedia_adapters import (
    collection_digest,
    collection_event,
    collection_event_to_memory_item,
)

SOURCE_SEMANTICS = {
    "repository_a": "Apeloff1/Lorebuffa",
    "repository_b": "Apeloff1/Openworld",
    "path": "backend/encyclopedia_routes.py",
    "shared_blob": "e842d3697187503b1e1da2df3563d797777c6bfb",
    "equivalence": "byte-identical source; catalog-independent collection policy promoted once",
}
NOW = datetime(2026, 9, 15, 15, 0, tzinfo=timezone.utc)


def _two_catch_collection(*, reverse: bool):
    events = (
        ("trout", 40, NOW),
        ("trout", 65, NOW + timedelta(minutes=5)),
    )
    if reverse:
        events = tuple(reversed(events))
    collection = empty_collection()
    for fish_id, size, occurred_at in events:
        collection = record_fish_catch(
            collection,
            fish_id=fish_id,
            size=size,
            occurred_at=occurred_at,
        ).collection
    return collection


def run_benchmark(*, iterations: int = 2000) -> dict[str, Any]:
    if isinstance(iterations, bool) or not isinstance(iterations, int):
        raise TypeError("iterations must be an integer")
    if iterations < 1:
        raise ValueError("iterations must be positive")

    forward = _two_catch_collection(reverse=False)
    reverse = _two_catch_collection(reverse=True)
    if collection_digest(forward) != collection_digest(reverse):
        raise AssertionError("out-of-order catch replay did not converge")

    catalog = {
        "id": "leviathan",
        "name": "The Leviathan",
        "description": "Ancient guardian",
        "facts": ["Rare"],
        "discovery_level": 75,
    }
    masked = project_fish_entry(catalog, empty_collection(), player_level=10)
    if masked["name"] != "???" or masked["description"] != "???":
        raise AssertionError("undiscovered catalog masking failed")

    started = time.perf_counter_ns()
    projections = 0
    caught_total = 0
    stable_digests: set[str] = set()
    for index in range(iterations):
        collection = _two_catch_collection(reverse=bool(index % 2))
        stable_digests.add(collection_digest(collection))
        summary = collection_summary(collection)
        if summary.total_fish_caught != 2:
            raise AssertionError("collection caught total mismatch")
        if summary.largest_catch_id != "trout" or summary.largest_catch_size != 65:
            raise AssertionError("largest collection catch mismatch")
        if collection_completion_percent(collection, ("trout", "bass")) != 50.0:
            raise AssertionError("collection completion mismatch")

        event = collection_event(
            collection,
            subject_id=f"player-{index}",
            fish_id="trout",
            action="fish_caught",
            occurred_at=NOW + timedelta(minutes=5),
        )
        memory = collection_event_to_memory_item(event)
        if memory["metadata"]["total_fish_caught"] != 2:
            raise AssertionError("collection memory count mismatch")
        projections += 1
        caught_total += summary.total_fish_caught

    elapsed_ns = time.perf_counter_ns() - started
    if projections != iterations:
        raise AssertionError("collection memory projection accounting mismatch")
    if caught_total != iterations * 2:
        raise AssertionError("collection catch accounting mismatch")
    if len(stable_digests) != 1:
        raise AssertionError("equivalent collection states produced unstable digests")

    elapsed_seconds = elapsed_ns / 1_000_000_000
    return {
        "workload": "frontier-encyclopedia-collection-v1",
        "source_semantics": SOURCE_SEMANTICS,
        "configuration": {"iterations": iterations},
        "evidence": {
            "memory_projections": projections,
            "caught_total": caught_total,
            "stable_state_digests": len(stable_digests),
            "replay_converges": True,
            "catalog_masking_holds": True,
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

#!/usr/bin/env python3
"""Benchmark frontier durable-event behavior without creating a latency gate.

The workload exercises the canonical ``EventBus`` plus ``SQLiteEventJournal``
through the same semantics promoted from GameForge: journal-before-delivery,
no-subscriber retention, bounded pending capacity, explicit ordered replay and
backpressure instead of dropping work. Timings are emitted as evidence only;
CI should assert behavior and counts, never machine-dependent speed thresholds.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
import time
from pathlib import Path
from typing import Any

from skeleton.frontier.events import DomainEvent, EventBus, SQLiteEventJournal


_SOURCE_BLOB = "481fcfca5a23272b70353eb09b7c3406bbc9bdd9"


def _ops_per_second(operations: int, elapsed_ns: int) -> float | None:
    if elapsed_ns <= 0:
        return None
    return operations / (elapsed_ns / 1_000_000_000)


async def run_benchmark(*, events: int, replay_batch: int) -> dict[str, Any]:
    if events < 1:
        raise ValueError("events must be positive")
    if replay_batch < 1:
        raise ValueError("replay_batch must be positive")

    with tempfile.TemporaryDirectory(prefix="frontier-events-") as directory:
        root = Path(directory)
        journal_path = root / "events.sqlite3"

        journal = SQLiteEventJournal(journal_path, capacity=events)
        try:
            bus = EventBus(journal=journal)
            write_started = time.perf_counter_ns()
            for index in range(events):
                delivered = await bus.publish(
                    DomainEvent.create(
                        "benchmark.runtime.completed",
                        {"seq": index, "status": "ok"},
                    )
                )
                if delivered != 0:
                    raise AssertionError("benchmark publish unexpectedly had subscribers")
            write_elapsed = time.perf_counter_ns() - write_started
            pending_before_reopen = await journal.pending_count()
        finally:
            journal.close()

        reopened = SQLiteEventJournal(journal_path, capacity=events)
        seen: list[int] = []
        try:
            recovered = EventBus(journal=reopened)

            async def handler(event: DomainEvent) -> None:
                seen.append(int(event.payload["seq"]))

            await recovered.subscribe("benchmark.runtime.completed", handler)
            replay_started = time.perf_counter_ns()
            replayed = 0
            replay_batches = 0
            while await reopened.pending_count():
                batch_count = await recovered.replay_pending(limit=replay_batch)
                if batch_count == 0:
                    raise RuntimeError("pending event replay made no progress")
                replayed += batch_count
                replay_batches += 1
            replay_elapsed = time.perf_counter_ns() - replay_started
            pending_after_replay = await reopened.pending_count()
        finally:
            reopened.close()

        pressure_path = root / "backpressure.sqlite3"
        pressure_journal = SQLiteEventJournal(pressure_path, capacity=1)
        try:
            pressure_bus = EventBus(journal=pressure_journal)
            first = DomainEvent.create("benchmark.pressure", {"seq": 1})
            second = DomainEvent.create("benchmark.pressure", {"seq": 2})
            assert await pressure_bus.publish(first) == 0

            backpressure_observed = False
            try:
                await pressure_bus.publish(second)
            except RuntimeError as exc:
                backpressure_observed = "backpressured, not dropped" in str(exc)

            recovered_pressure: list[int] = []

            async def pressure_handler(event: DomainEvent) -> None:
                recovered_pressure.append(int(event.payload["seq"]))

            await pressure_bus.subscribe("benchmark.pressure", pressure_handler)
            pressure_replayed = await pressure_bus.replay_pending()
            pressure_pending_after = await pressure_journal.pending_count()
        finally:
            pressure_journal.close()

    return {
        "workload": "frontier-event-journal-v1",
        "source_semantics": {
            "repository": "Apeloff1/gameforge-rs",
            "path": "crates/gf-core/src/lib.rs",
            "blob": _SOURCE_BLOB,
        },
        "configuration": {
            "events": events,
            "replay_batch": replay_batch,
        },
        "evidence": {
            "journaled_events": events,
            "pending_before_reopen": pending_before_reopen,
            "replayed_events": replayed,
            "replay_batches": replay_batches,
            "pending_after_replay": pending_after_replay,
            "ordered_replay": seen == list(range(events)),
            "backpressure_observed": backpressure_observed,
            "backpressure_replayed": pressure_replayed,
            "backpressure_recovered_sequence": recovered_pressure,
            "backpressure_pending_after": pressure_pending_after,
        },
        "timing": {
            "journal_seconds": write_elapsed / 1_000_000_000,
            "replay_seconds": replay_elapsed / 1_000_000_000,
            "journal_ops_per_second": _ops_per_second(events, write_elapsed),
            "replay_ops_per_second": _ops_per_second(replayed, replay_elapsed),
        },
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=int, default=1000)
    parser.add_argument("--replay-batch", type=int, default=100)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    report = asyncio.run(
        run_benchmark(events=args.events, replay_batch=args.replay_batch)
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

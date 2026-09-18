"""Deterministic load/soak profiles for the durable SQLite run store."""
from __future__ import annotations

import asyncio
import math
import sqlite3
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from skeleton.state import RunStatus, SQLiteRunStore, StepStatus


@dataclass(frozen=True, slots=True)
class StateProfileResult:
    mode: str
    operations: int
    completed: int
    failed: int
    run_rows: int
    step_rows: int
    checkpoint_rows: int
    recoverable: int
    revision: int
    p50_ms: float
    p95_ms: float
    max_ms: float


@dataclass(frozen=True, slots=True)
class StorageFailureProfileResult:
    """Outcome of deterministic storage-unavailability injection and recovery."""

    injected_failures: int
    observed_failures: int
    successful_retries: int
    run_rows: int
    step_rows: int
    checkpoint_rows: int
    checkpoint_revision: int
    replay_steps: int
    recoverable: int
    terminal_status: RunStatus
    terminal_revision: int


class _ConnectFailureStore(SQLiteRunStore):
    """SQLite store that can fail exactly the next connection attempt."""

    def __init__(self, path: str | Path) -> None:
        self._connect_failures_remaining = 0
        super().__init__(path)

    def fail_next_connect(self) -> None:
        self._connect_failures_remaining += 1

    def _connect(self) -> sqlite3.Connection:
        if self._connect_failures_remaining:
            self._connect_failures_remaining -= 1
            raise sqlite3.OperationalError("injected storage unavailable")
        return super()._connect()


def _positive(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 1:
        raise ValueError(f"{name} must be at least 1")
    return value


def _percentile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = max(0, math.ceil(len(ordered) * fraction) - 1)
    return ordered[index]


def _counts(path: Path) -> tuple[int, int, int]:
    conn = sqlite3.connect(str(path))
    try:
        runs = int(conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0])
        steps = int(conn.execute("SELECT COUNT(*) FROM steps").fetchone()[0])
        checkpoints = int(conn.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0])
        return runs, steps, checkpoints
    finally:
        conn.close()


def _result(
    *, mode: str, operations: int, completed: int, failed: int,
    path: Path, store: SQLiteRunStore, revision: int,
    durations: Sequence[float],
) -> StateProfileResult:
    run_rows, step_rows, checkpoint_rows = _counts(path)
    return StateProfileResult(
        mode=mode,
        operations=operations,
        completed=completed,
        failed=failed,
        run_rows=run_rows,
        step_rows=step_rows,
        checkpoint_rows=checkpoint_rows,
        recoverable=len(store.list_recoverable(limit=10_000)),
        revision=revision,
        p50_ms=round(_percentile(durations, 0.50), 3),
        p95_ms=round(_percentile(durations, 0.95), 3),
        max_ms=round(max(durations, default=0.0), 3),
    )


async def run_state_lifecycle_pressure_profile(
    *, runs: int = 64, concurrency: int = 8, steps_per_run: int = 3,
) -> StateProfileResult:
    """Run independent durable lifecycles concurrently against one database."""
    runs = _positive(runs, "runs")
    concurrency = min(_positive(concurrency, "concurrency"), runs)
    steps_per_run = _positive(steps_per_run, "steps_per_run")

    with tempfile.TemporaryDirectory(prefix="skeleton-state-pressure-") as tmp:
        path = Path(tmp) / "runs.sqlite3"
        store = SQLiteRunStore(path)
        semaphore = asyncio.Semaphore(concurrency)

        async def one(index: int) -> tuple[bool, float]:
            async with semaphore:
                started = time.perf_counter()
                run_id = f"pressure-{index}"
                worker = f"worker-{index % concurrency}"

                def lifecycle() -> None:
                    store.create_run(run_id, {"index": index})
                    store.claim_run(run_id, worker, lease_seconds=300.0)
                    last_step = ""
                    for number in range(1, steps_per_run + 1):
                        step_id = f"step-{number}"
                        store.start_step(
                            run_id, step_id, "reliability",
                            worker_id=worker, payload={"step": number},
                        )
                        store.finish_step(
                            run_id, step_id, StepStatus.SUCCEEDED,
                            worker_id=worker, result={"ok": True},
                        )
                        last_step = step_id
                    store.checkpoint(
                        run_id, {"steps": steps_per_run},
                        worker_id=worker, after_step_id=last_step,
                    )
                    store.transition_run(
                        run_id, RunStatus.SUCCEEDED,
                        worker_id=worker, output={"ok": True},
                    )

                try:
                    await asyncio.to_thread(lifecycle)
                except Exception:
                    ok = False
                else:
                    ok = True
                return ok, (time.perf_counter() - started) * 1000.0

        outcomes = await asyncio.gather(*(one(index) for index in range(runs)))
        completed = sum(ok for ok, _ in outcomes)
        durations = [duration for _, duration in outcomes]
        return _result(
            mode="lifecycle",
            operations=runs * steps_per_run,
            completed=completed,
            failed=runs - completed,
            path=path,
            store=store,
            revision=0,
            durations=durations,
        )


def run_state_heartbeat_soak_profile(*, heartbeats: int = 500) -> StateProfileResult:
    """Renew one live lease repeatedly and prove state rows do not grow."""
    heartbeats = _positive(heartbeats, "heartbeats")
    durations: list[float] = []
    with tempfile.TemporaryDirectory(prefix="skeleton-state-heartbeat-") as tmp:
        path = Path(tmp) / "runs.sqlite3"
        store = SQLiteRunStore(path)
        store.create_run("heartbeat-soak", {"profile": "heartbeat"})
        record = store.claim_run("heartbeat-soak", "worker", lease_seconds=86_400.0)
        for _ in range(heartbeats):
            started = time.perf_counter()
            record = store.heartbeat(
                "heartbeat-soak", "worker",
                lease_seconds=86_400.0,
                expected_revision=record.revision,
            )
            durations.append((time.perf_counter() - started) * 1000.0)
        record = store.transition_run(
            "heartbeat-soak", RunStatus.SUCCEEDED,
            worker_id="worker", expected_revision=record.revision,
            output={"heartbeats": heartbeats},
        )
        return _result(
            mode="heartbeat",
            operations=heartbeats,
            completed=1,
            failed=0,
            path=path,
            store=store,
            revision=record.revision,
            durations=durations,
        )


def run_state_storage_failure_recovery_profile() -> StorageFailureProfileResult:
    """Inject connection failures at each write stage and prove clean retry recovery.

    The fault is raised before a SQLite connection is returned, modeling a
    temporarily unavailable storage boundary. Every interrupted operation is
    retried once with the same semantic identity so the profile also proves
    that recovery does not duplicate durable rows or advance revisions twice.
    """

    with tempfile.TemporaryDirectory(prefix="skeleton-state-storage-chaos-") as tmp:
        path = Path(tmp) / "runs.sqlite3"
        store = _ConnectFailureStore(path)
        run_id = "storage-chaos"
        worker = "worker"
        observed_failures = 0
        successful_retries = 0

        store.create_run(run_id, {"profile": "storage-failure"})

        def interrupted(operation):
            nonlocal observed_failures, successful_retries
            store.fail_next_connect()
            try:
                operation()
            except sqlite3.OperationalError as exc:
                if str(exc) != "injected storage unavailable":
                    raise
                observed_failures += 1
            else:
                raise AssertionError("injected storage failure was not observed")
            result = operation()
            successful_retries += 1
            return result

        claimed = interrupted(
            lambda: store.claim_run(
                run_id,
                worker,
                lease_seconds=300.0,
                expected_revision=0,
            )
        )
        interrupted(
            lambda: store.start_step(
                run_id,
                "step-1",
                "reliability",
                worker_id=worker,
                payload={"attempt": 1},
                effect_key="storage-chaos-effect",
            )
        )
        interrupted(
            lambda: store.finish_step(
                run_id,
                "step-1",
                StepStatus.SUCCEEDED,
                worker_id=worker,
                result={"ok": True},
            )
        )
        checkpoint = interrupted(
            lambda: store.checkpoint(
                run_id,
                {"step": 1},
                worker_id=worker,
                after_step_id="step-1",
            )
        )
        terminal = interrupted(
            lambda: store.transition_run(
                run_id,
                RunStatus.SUCCEEDED,
                worker_id=worker,
                expected_revision=claimed.revision,
                output={"recovered": True},
            )
        )

        run_rows, step_rows, checkpoint_rows = _counts(path)
        resume = store.resume_state(run_id)
        return StorageFailureProfileResult(
            injected_failures=5,
            observed_failures=observed_failures,
            successful_retries=successful_retries,
            run_rows=run_rows,
            step_rows=step_rows,
            checkpoint_rows=checkpoint_rows,
            checkpoint_revision=checkpoint.revision,
            replay_steps=len(resume.replay_steps),
            recoverable=len(store.list_recoverable(limit=10_000)),
            terminal_status=terminal.status,
            terminal_revision=terminal.revision,
        )

"""Regression coverage for durable-state load, soak, and lease chaos."""
from __future__ import annotations

import asyncio
import tempfile
import threading
from pathlib import Path

from skeleton.state import RunStatus, SQLiteRunStore, StateConflict
from skeleton.testing.state_reliability_profiles import (
    run_state_heartbeat_soak_profile,
    run_state_lifecycle_pressure_profile,
)


def test_concurrent_state_lifecycle_pressure_is_structurally_bounded() -> None:
    result = asyncio.run(
        run_state_lifecycle_pressure_profile(
            runs=24,
            concurrency=6,
            steps_per_run=3,
        )
    )

    assert result.completed == 24
    assert result.failed == 0
    assert result.operations == 72
    assert result.run_rows == 24
    assert result.step_rows == 72
    assert result.checkpoint_rows == 24
    assert result.recoverable == 0
    assert result.p50_ms >= 0.0
    assert result.p95_ms >= result.p50_ms
    assert result.max_ms >= result.p95_ms


def test_heartbeat_soak_updates_in_place_without_state_row_growth() -> None:
    result = run_state_heartbeat_soak_profile(heartbeats=128)

    assert result.completed == 1
    assert result.failed == 0
    assert result.revision == 130
    assert result.run_rows == 1
    assert result.step_rows == 0
    assert result.checkpoint_rows == 0
    assert result.recoverable == 0


class _Clock:
    def __init__(self) -> None:
        self._value = 1_000.0
        self._lock = threading.Lock()

    def __call__(self) -> float:
        with self._lock:
            return self._value

    def advance(self, seconds: float) -> None:
        with self._lock:
            self._value += seconds


def test_live_lease_contention_has_one_owner_then_recovers_after_expiry() -> None:
    clock = _Clock()
    with tempfile.TemporaryDirectory(prefix="skeleton-state-contention-") as tmp:
        store = SQLiteRunStore(Path(tmp) / "runs.sqlite3", clock=clock)
        store.create_run("contended", {"profile": "lease-chaos"})

        async def scenario() -> list[bool]:
            async def claim(index: int) -> bool:
                try:
                    await asyncio.to_thread(
                        store.claim_run,
                        "contended",
                        f"worker-{index}",
                        lease_seconds=30.0,
                    )
                except StateConflict:
                    return False
                return True

            return await asyncio.gather(*(claim(index) for index in range(12)))

        acquired = asyncio.run(scenario())
        assert sum(acquired) == 1

        clock.advance(31.0)
        recovered = store.claim_run(
            "contended",
            "recovery-worker",
            lease_seconds=30.0,
        )
        terminal = store.transition_run(
            "contended",
            RunStatus.SUCCEEDED,
            worker_id="recovery-worker",
            expected_revision=recovered.revision,
            output={"recovered": True},
        )

        assert terminal.revision == 3
        assert store.list_recoverable() == ()


def test_state_profiles_reject_invalid_pressure_configuration() -> None:
    async def scenario() -> None:
        try:
            await run_state_lifecycle_pressure_profile(runs=0)
        except ValueError as exc:
            assert "runs must be at least 1" in str(exc)
        else:
            raise AssertionError("zero-run pressure profile was accepted")

    asyncio.run(scenario())

    try:
        run_state_heartbeat_soak_profile(heartbeats=True)
    except TypeError as exc:
        assert "heartbeats must be an integer" in str(exc)
    else:
        raise AssertionError("boolean heartbeat count was accepted")

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import threading

import pytest

from skeleton.intelligence.admission import (
    AdmissionRequest,
    ResourceBudget,
    RuntimePressure,
    UsageEstimate,
)
from skeleton.intelligence.admission_runtime import AdmissionRuntime
from skeleton.intelligence.quota import (
    QuotaConflict,
    QuotaExceeded,
    TenantQuota,
)
from skeleton.intelligence.quota_sqlite import SqliteTenantQuotaLedger


def _quota(
    *,
    max_operations: int = 10,
    max_input_tokens: int = 10_000,
    max_storage_bytes: int = 10_000_000,
    max_concurrent: int = 10,
) -> TenantQuota:
    return TenantQuota(
        window_id="window-1",
        max_operations=max_operations,
        max_input_tokens=max_input_tokens,
        max_output_tokens=10_000,
        max_cost_usd=100.0,
        max_tool_calls=1_000,
        max_artifact_bytes=10_000_000,
        max_storage_bytes=max_storage_bytes,
        max_concurrent_operations=max_concurrent,
    )


def _request(operation_id: str) -> AdmissionRequest:
    return AdmissionRequest(
        operation_id=operation_id,
        tenant_id="tenant-a",
        capability="model-inference",
        budget=ResourceBudget(
            max_input_tokens=1_000,
            max_output_tokens=1_000,
            max_cost_usd=10.0,
            max_wall_seconds=30.0,
            max_provider_attempts=3,
            max_tool_calls=10,
            max_artifact_bytes=1024,
            max_storage_bytes=1024,
            max_concurrency=4,
            max_queue_depth=20,
        ),
        estimate=UsageEstimate(
            input_tokens=100,
            output_tokens=25,
            cost_usd=0.5,
            wall_seconds=1.0,
            provider_attempts=1,
        ),
        pressure=RuntimePressure(),
    )


def test_active_reservation_survives_process_restart(tmp_path: Path) -> None:
    path = tmp_path / "quota.sqlite3"
    first = SqliteTenantQuotaLedger(path)
    first.configure("tenant-a", _quota())
    estimate = UsageEstimate(input_tokens=100, cost_usd=1.0)

    reservation = first.reserve("tenant-a", "op-1", estimate, now=10.0)

    restarted = SqliteTenantQuotaLedger(path)
    snapshot = restarted.snapshot("tenant-a")
    replay = restarted.reserve("tenant-a", "op-1", estimate, now=99.0)

    assert snapshot["active_reservations"] == 1
    assert snapshot["reserved"]["input_tokens"] == 100
    assert replay == reservation
    assert replay.reserved_at == 10.0


def test_completion_and_committed_usage_survive_restart(tmp_path: Path) -> None:
    path = tmp_path / "quota.sqlite3"
    ledger = SqliteTenantQuotaLedger(path)
    ledger.configure("tenant-a", _quota())
    reservation = ledger.reserve(
        "tenant-a",
        "op-1",
        UsageEstimate(input_tokens=100, cost_usd=1.0),
        now=10.0,
    )
    ledger.complete(
        reservation.reservation_id,
        UsageEstimate(input_tokens=80, cost_usd=0.75),
        now=11.0,
    )

    restarted = SqliteTenantQuotaLedger(path)
    snapshot = restarted.snapshot("tenant-a")
    completion = restarted.completion_for_operation("tenant-a", "op-1")

    assert snapshot["active_reservations"] == 0
    assert snapshot["committed"]["operations"] == 1
    assert snapshot["committed"]["input_tokens"] == 80
    assert snapshot["committed"]["cost_usd"] == 0.75
    assert completion is not None
    assert completion.actual.input_tokens == 80

    with pytest.raises(QuotaConflict, match="already completed"):
        restarted.reserve(
            "tenant-a",
            "op-1",
            UsageEstimate(input_tokens=100, cost_usd=1.0),
        )


def test_two_workers_cannot_overbook_single_operation_window(
    tmp_path: Path,
) -> None:
    path = tmp_path / "quota.sqlite3"
    setup = SqliteTenantQuotaLedger(path)
    setup.configure(
        "tenant-a",
        _quota(max_operations=1, max_concurrent=10),
    )

    left = SqliteTenantQuotaLedger(path)
    right = SqliteTenantQuotaLedger(path)
    barrier = threading.Barrier(2)

    def attempt(ledger: SqliteTenantQuotaLedger, operation: str):
        barrier.wait(timeout=5)
        try:
            return (
                "ok",
                ledger.reserve(
                    "tenant-a",
                    operation,
                    UsageEstimate(input_tokens=1),
                ).operation_id,
            )
        except QuotaExceeded as exc:
            return ("denied", str(exc))

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda args: attempt(*args),
                [(left, "op-a"), (right, "op-b")],
            )
        )

    assert sorted(result[0] for result in results) == ["denied", "ok"]
    snapshot = SqliteTenantQuotaLedger(path).snapshot("tenant-a")
    assert snapshot["active_reservations"] == 1
    assert snapshot["reserved"]["operations"] == 1


def test_same_operation_race_is_retry_stable_across_workers(
    tmp_path: Path,
) -> None:
    path = tmp_path / "quota.sqlite3"
    setup = SqliteTenantQuotaLedger(path)
    setup.configure("tenant-a", _quota(max_operations=1))
    first = SqliteTenantQuotaLedger(path)
    second = SqliteTenantQuotaLedger(path)
    barrier = threading.Barrier(2)
    estimate = UsageEstimate(input_tokens=10, cost_usd=0.1)

    def attempt(ledger: SqliteTenantQuotaLedger):
        barrier.wait(timeout=5)
        return ledger.reserve("tenant-a", "same-op", estimate)

    with ThreadPoolExecutor(max_workers=2) as pool:
        reservations = list(pool.map(attempt, [first, second]))

    assert reservations[0].reservation_id == reservations[1].reservation_id
    assert SqliteTenantQuotaLedger(path).snapshot("tenant-a")[
        "active_reservations"
    ] == 1


def test_cumulative_quota_is_shared_between_ledger_instances(
    tmp_path: Path,
) -> None:
    path = tmp_path / "quota.sqlite3"
    first = SqliteTenantQuotaLedger(path)
    first.configure("tenant-a", _quota(max_input_tokens=100))
    second = SqliteTenantQuotaLedger(path)

    first.reserve(
        "tenant-a",
        "op-1",
        UsageEstimate(input_tokens=60),
    )

    with pytest.raises(QuotaExceeded, match="input_tokens"):
        second.reserve(
            "tenant-a",
            "op-2",
            UsageEstimate(input_tokens=41),
        )


def test_admission_runtime_restart_reuses_durable_reservation(
    tmp_path: Path,
) -> None:
    path = tmp_path / "quota.sqlite3"
    first_ledger = SqliteTenantQuotaLedger(path)
    first_ledger.configure("tenant-a", _quota())
    request = _request("op-runtime")

    first_runtime = AdmissionRuntime(quota_ledger=first_ledger)
    first_lease = first_runtime.admit(request, now_wall=10.0)
    assert first_lease.quota_reservation is not None

    restarted_ledger = SqliteTenantQuotaLedger(path)
    restarted_runtime = AdmissionRuntime(quota_ledger=restarted_ledger)
    restarted_lease = restarted_runtime.admit(request, now_wall=20.0)

    assert restarted_lease.quota_reservation is not None
    assert (
        restarted_lease.quota_reservation.reservation_id
        == first_lease.quota_reservation.reservation_id
    )
    assert restarted_ledger.snapshot("tenant-a")["active_reservations"] == 1

    restarted_runtime.complete(
        "op-runtime",
        UsageEstimate(input_tokens=75, output_tokens=20, cost_usd=0.4),
        now_wall=21.0,
    )
    assert SqliteTenantQuotaLedger(path).snapshot("tenant-a")[
        "committed"
    ]["input_tokens"] == 75


def test_window_reset_is_durable_and_fenced_by_active_reservations(
    tmp_path: Path,
) -> None:
    path = tmp_path / "quota.sqlite3"
    ledger = SqliteTenantQuotaLedger(path)
    ledger.configure("tenant-a", _quota())
    reservation = ledger.reserve(
        "tenant-a",
        "op-1",
        UsageEstimate(input_tokens=10),
    )

    with pytest.raises(QuotaConflict, match="active"):
        ledger.reset_window(
            "tenant-a",
            TenantQuota(window_id="window-2"),
        )

    ledger.release(reservation.reservation_id)
    ledger.reset_window(
        "tenant-a",
        TenantQuota(window_id="window-2"),
    )

    restarted = SqliteTenantQuotaLedger(path)
    snapshot = restarted.snapshot("tenant-a")
    assert snapshot["window_id"] == "window-2"
    assert snapshot["committed"]["operations"] == 0

def test_storage_usage_is_independent_and_survives_restart(
    tmp_path: Path,
) -> None:
    path = tmp_path / "quota.sqlite3"
    ledger = SqliteTenantQuotaLedger(path)
    ledger.configure(
        "tenant-a",
        _quota(max_storage_bytes=64),
    )
    runtime = AdmissionRuntime(quota_ledger=ledger)
    runtime.admit(_request("op-storage"), now_wall=10.0)

    event = runtime.meter_storage_bytes(
        "op-storage",
        "storage-write-1",
        48,
        now_wall=10.1,
    )
    assert event.delta.storage_bytes == 48
    assert event.delta.artifact_bytes == 0

    runtime.complete(
        "op-storage",
        UsageEstimate(
            input_tokens=80,
            output_tokens=20,
            cost_usd=0.4,
            wall_seconds=0.8,
            provider_attempts=1,
        ),
        now_wall=11.0,
    )

    restarted = SqliteTenantQuotaLedger(path)
    snapshot = restarted.snapshot("tenant-a")
    assert snapshot["committed"]["storage_bytes"] == 48
    assert snapshot["committed"]["artifact_bytes"] == 0
    assert snapshot["metered_by_category"]["storage"]["storage_bytes"] == 48
    assert snapshot["metered_by_category"]["storage"]["artifact_bytes"] == 0


def test_legacy_quota_schema_migrates_storage_columns_in_place(
    tmp_path: Path,
) -> None:
    path = tmp_path / "legacy-quota.sqlite3"
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE tenant_quota (
                tenant_id TEXT PRIMARY KEY,
                window_id TEXT NOT NULL,
                max_operations INTEGER NOT NULL,
                max_input_tokens INTEGER NOT NULL,
                max_output_tokens INTEGER NOT NULL,
                max_cost_usd REAL NOT NULL,
                max_tool_calls INTEGER NOT NULL,
                max_artifact_bytes INTEGER NOT NULL,
                max_concurrent_operations INTEGER NOT NULL,
                committed_operations INTEGER NOT NULL DEFAULT 0,
                committed_input_tokens INTEGER NOT NULL DEFAULT 0,
                committed_output_tokens INTEGER NOT NULL DEFAULT 0,
                committed_cost_usd REAL NOT NULL DEFAULT 0,
                committed_tool_calls INTEGER NOT NULL DEFAULT 0,
                committed_artifact_bytes INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE quota_reservations (
                reservation_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                window_id TEXT NOT NULL,
                operation_id TEXT NOT NULL,
                estimate_operations INTEGER NOT NULL,
                estimate_input_tokens INTEGER NOT NULL,
                estimate_output_tokens INTEGER NOT NULL,
                estimate_cost_usd REAL NOT NULL,
                estimate_tool_calls INTEGER NOT NULL,
                estimate_artifact_bytes INTEGER NOT NULL,
                reserved_at REAL NOT NULL,
                UNIQUE (tenant_id, operation_id)
            );
            CREATE TABLE quota_completions (
                reservation_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                window_id TEXT NOT NULL,
                operation_id TEXT NOT NULL,
                estimate_operations INTEGER NOT NULL,
                estimate_input_tokens INTEGER NOT NULL,
                estimate_output_tokens INTEGER NOT NULL,
                estimate_cost_usd REAL NOT NULL,
                estimate_tool_calls INTEGER NOT NULL,
                estimate_artifact_bytes INTEGER NOT NULL,
                actual_operations INTEGER NOT NULL,
                actual_input_tokens INTEGER NOT NULL,
                actual_output_tokens INTEGER NOT NULL,
                actual_cost_usd REAL NOT NULL,
                actual_tool_calls INTEGER NOT NULL,
                actual_artifact_bytes INTEGER NOT NULL,
                overrun_dimensions TEXT NOT NULL,
                completed_at REAL NOT NULL,
                UNIQUE (tenant_id, operation_id)
            );
            CREATE TABLE quota_usage_events (
                event_id TEXT PRIMARY KEY,
                reservation_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                window_id TEXT NOT NULL,
                operation_id TEXT NOT NULL,
                category TEXT NOT NULL,
                delta_operations INTEGER NOT NULL DEFAULT 0,
                delta_input_tokens INTEGER NOT NULL DEFAULT 0,
                delta_output_tokens INTEGER NOT NULL DEFAULT 0,
                delta_cost_usd REAL NOT NULL DEFAULT 0,
                delta_tool_calls INTEGER NOT NULL DEFAULT 0,
                delta_artifact_bytes INTEGER NOT NULL DEFAULT 0,
                recorded_at REAL NOT NULL
            );
            """
        )
        conn.execute(
            """
            INSERT INTO tenant_quota (
                tenant_id, window_id,
                max_operations, max_input_tokens, max_output_tokens,
                max_cost_usd, max_tool_calls, max_artifact_bytes,
                max_concurrent_operations
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "tenant-a",
                "legacy-window",
                10,
                1000,
                1000,
                50.0,
                100,
                4096,
                4,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    migrated = SqliteTenantQuotaLedger(path)
    snapshot = migrated.snapshot("tenant-a")

    assert snapshot["quota"]["max_artifact_bytes"] == 4096
    assert snapshot["quota"]["max_storage_bytes"] == 4096
    assert snapshot["committed"]["storage_bytes"] == 0

    conn = sqlite3.connect(path)
    try:
        columns = {
            table: {
                row[1]
                for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
            }
            for table in (
                "tenant_quota",
                "quota_reservations",
                "quota_completions",
                "quota_usage_events",
            )
        }
    finally:
        conn.close()

    assert "max_storage_bytes" in columns["tenant_quota"]
    assert "committed_storage_bytes" in columns["tenant_quota"]
    assert "estimate_storage_bytes" in columns["quota_reservations"]
    assert "estimate_storage_bytes" in columns["quota_completions"]
    assert "actual_storage_bytes" in columns["quota_completions"]
    assert "delta_storage_bytes" in columns["quota_usage_events"]

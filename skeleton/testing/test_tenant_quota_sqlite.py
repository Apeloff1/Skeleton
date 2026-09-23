from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
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



def test_incremental_tool_artifact_storage_usage_survives_restart(
    tmp_path: Path,
) -> None:
    path = tmp_path / "quota.sqlite3"
    ledger = SqliteTenantQuotaLedger(path)
    ledger.configure("tenant-a", _quota())
    reservation = ledger.reserve(
        "tenant-a",
        "op-metered",
        UsageEstimate(input_tokens=10),
        now=10.0,
    )

    ledger.record_usage_event(
        reservation.reservation_id,
        "tool-1",
        "tool",
        UsageEstimate(tool_calls=1),
        max_tool_calls=10,
        max_artifact_bytes=1024,
        now=11.0,
    )
    ledger.record_usage_event(
        reservation.reservation_id,
        "artifact-1",
        "artifact",
        UsageEstimate(artifact_bytes=256),
        max_tool_calls=10,
        max_artifact_bytes=1024,
        now=12.0,
    )
    ledger.record_usage_event(
        reservation.reservation_id,
        "storage-1",
        "storage",
        UsageEstimate(artifact_bytes=128),
        max_tool_calls=10,
        max_artifact_bytes=1024,
        now=13.0,
    )

    restarted = SqliteTenantQuotaLedger(path)
    metered = restarted.metered_usage(reservation.reservation_id)
    snapshot = restarted.snapshot("tenant-a")

    assert metered.tool_calls == 1
    assert metered.artifact_bytes == 384
    assert snapshot["usage_events"] == 3
    assert snapshot["metered_by_category"]["tool"]["tool_calls"] == 1
    assert snapshot["metered_by_category"]["artifact"]["artifact_bytes"] == 256
    assert snapshot["metered_by_category"]["storage"]["artifact_bytes"] == 128

    completion = restarted.complete(
        reservation.reservation_id,
        UsageEstimate(input_tokens=8),
        now=14.0,
    )
    assert completion.actual.input_tokens == 8
    assert completion.actual.tool_calls == 1
    assert completion.actual.artifact_bytes == 384


def test_unknown_actual_usage_marker_survives_restart_and_blocks_completion(
    tmp_path: Path,
) -> None:
    path = tmp_path / "quota.sqlite3"
    ledger = SqliteTenantQuotaLedger(path)
    ledger.configure("tenant-a", _quota())
    reservation = ledger.reserve(
        "tenant-a",
        "op-unknown",
        UsageEstimate(),
        now=10.0,
    )
    marker = ledger.mark_usage_unknown(
        reservation.reservation_id,
        "storage-unknown-1",
        "storage",
        now=11.0,
    )
    assert marker.category == "unknown:storage"

    restarted = SqliteTenantQuotaLedger(path)
    unresolved = restarted.unresolved_usage(reservation.reservation_id)
    assert [item.event_id for item in unresolved] == ["storage-unknown-1"]
    assert restarted.snapshot("tenant-a")["unknown_usage_events"] == 1

    with pytest.raises(QuotaConflict, match="actual_usage_unknown:storage"):
        restarted.complete(
            reservation.reservation_id,
            UsageEstimate(),
            now=12.0,
        )

    resolved = restarted.resolve_unknown_usage(
        reservation.reservation_id,
        "storage-unknown-1",
        UsageEstimate(artifact_bytes=512),
        max_tool_calls=10,
        max_artifact_bytes=1024,
        now=13.0,
    )
    assert resolved.category == "storage"
    assert resolved.delta.artifact_bytes == 512
    assert SqliteTenantQuotaLedger(path).unresolved_usage(
        reservation.reservation_id
    ) == ()

    completion = SqliteTenantQuotaLedger(path).complete(
        reservation.reservation_id,
        UsageEstimate(),
        now=14.0,
    )
    assert completion.actual.artifact_bytes == 512


def test_incremental_usage_event_replay_is_stable_across_ledger_instances(
    tmp_path: Path,
) -> None:
    path = tmp_path / "quota.sqlite3"
    first = SqliteTenantQuotaLedger(path)
    first.configure("tenant-a", _quota())
    reservation = first.reserve(
        "tenant-a",
        "op-replay",
        UsageEstimate(),
        now=10.0,
    )
    event = first.record_usage_event(
        reservation.reservation_id,
        "tool-replay-1",
        "tool",
        UsageEstimate(tool_calls=1),
        max_tool_calls=10,
        max_artifact_bytes=1024,
        now=11.0,
    )

    second = SqliteTenantQuotaLedger(path)
    replay = second.record_usage_event(
        reservation.reservation_id,
        "tool-replay-1",
        "tool",
        UsageEstimate(tool_calls=1),
        max_tool_calls=10,
        max_artifact_bytes=1024,
        now=99.0,
    )

    assert replay == event
    assert second.metered_usage(reservation.reservation_id).tool_calls == 1

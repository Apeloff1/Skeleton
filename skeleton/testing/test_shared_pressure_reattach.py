from __future__ import annotations

import json
import sqlite3

import pytest

from skeleton.ai.runtime.observability.cost_governor import (
    CostGovernor,
    CostGovernorConflict,
    CostGovernorError,
)
from skeleton.intelligence.admission import (
    AdmissionRequest,
    ResourceBudget,
    UsageEstimate,
)
from skeleton.intelligence.quota import TenantQuota
from skeleton.intelligence.shared_pressure import (
    SharedPressurePolicy,
    SqliteSharedPressureLedger,
)


def _quota() -> TenantQuota:
    return TenantQuota(
        window_id="shared-reattach-quota",
        max_operations=100,
        max_input_tokens=100_000,
        max_output_tokens=100_000,
        max_cost_usd=100.0,
        max_tool_calls=100,
        max_artifact_bytes=10_000_000,
        max_storage_bytes=10_000_000,
        max_concurrent_operations=8,
    )


def _request(operation_id: str) -> AdmissionRequest:
    return AdmissionRequest(
        operation_id=operation_id,
        tenant_id="tenant-a",
        capability="model-inference",
        budget=ResourceBudget(
            max_input_tokens=10_000,
            max_output_tokens=5_000,
            max_cost_usd=5.0,
            max_wall_seconds=60.0,
            max_provider_attempts=4,
            max_tool_calls=20,
            max_artifact_bytes=1_000_000,
            max_storage_bytes=1_000_000,
            max_concurrency=4,
            max_queue_depth=100,
        ),
        estimate=UsageEstimate(
            input_tokens=100,
            output_tokens=20,
            cost_usd=0.5,
            wall_seconds=2.0,
            provider_attempts=1,
        ),
        priority=25,
    )


def _pressure(path) -> SqliteSharedPressureLedger:
    return SqliteSharedPressureLedger(path)


def _configure_pressure(path) -> SqliteSharedPressureLedger:
    ledger = _pressure(path)
    ledger.configure(
        SharedPressurePolicy(
            scope="ai-runtime",
            max_concurrency=4,
            max_queue_depth=100,
            max_tenant_concurrency=4,
            max_tenant_queue_depth=100,
            soft_shed_fraction=1.0,
            protect_priority_at_or_below=100,
            default_lease_seconds=60.0,
        ),
    )
    return ledger


def _governor(
    path,
    *,
    owner: str,
    pressure: SqliteSharedPressureLedger | None = None,
) -> CostGovernor:
    return CostGovernor.durable(
        path,
        default_tenant_quota=_quota(),
        shared_pressure_ledger=pressure,
        shared_pressure_scope=(
            None if pressure is None else "ai-runtime"
        ),
        shared_pressure_owner_id=(
            None if pressure is None else owner
        ),
    )


def test_shared_pressure_lease_survives_restart_and_releases_exactly(
    tmp_path,
) -> None:
    path = tmp_path / "runtime.sqlite3"
    pressure = _configure_pressure(path)
    request = _request("op-pressure-restart")
    first = _governor(path, owner="worker-a", pressure=pressure)

    original = first.reserve(request, now_wall=10.0)
    before = pressure.snapshot(
        "ai-runtime",
        tenant_id="tenant-a",
        now=20.0,
    )
    assert before.active == 1
    assert before.tenant_active == 1

    restarted_pressure = _pressure(path)
    restarted = _governor(
        path,
        owner="worker-a",
        pressure=restarted_pressure,
    )
    replay = restarted.reserve(request, now_wall=20.0)

    assert replay == original
    assert restarted.active_reservations() == (
        request.operation_id,
    )
    active = restarted.runtime._active[request.operation_id]
    assert active.lease.shared_pressure_lease is not None
    assert active.shared_pressure_lease == active.lease.shared_pressure_lease
    assert active.shared_pressure_lease.owner_id == "worker-a"

    decision = restarted.release_unspent(request.operation_id)
    assert decision.state == "released_unspent"
    after = restarted_pressure.snapshot(
        "ai-runtime",
        tenant_id="tenant-a",
        now=21.0,
    )
    assert after.active == 0
    assert restarted.runtime.quota_ledger.snapshot("tenant-a")[
        "active_reservations"
    ] == 0


def test_shared_pressure_owner_change_fails_closed_without_transfer(
    tmp_path,
) -> None:
    path = tmp_path / "runtime.sqlite3"
    pressure = _configure_pressure(path)
    request = _request("op-pressure-owner")
    first = _governor(path, owner="worker-a", pressure=pressure)
    first.reserve(request, now_wall=10.0)

    restarted_pressure = _pressure(path)
    restarted = _governor(
        path,
        owner="worker-b",
        pressure=restarted_pressure,
    )

    with pytest.raises(
        CostGovernorConflict,
        match="shared pressure lease identity does not match runtime",
    ):
        restarted.reserve(request, now_wall=20.0)

    snap = restarted_pressure.snapshot(
        "ai-runtime",
        tenant_id="tenant-a",
        now=20.0,
    )
    assert snap.active == 1
    assert restarted.runtime.quota_ledger.snapshot("tenant-a")[
        "active_reservations"
    ] == 1


def test_expired_shared_pressure_lease_is_not_reacquired_on_restart(
    tmp_path,
) -> None:
    path = tmp_path / "runtime.sqlite3"
    pressure = _configure_pressure(path)
    request = _request("op-pressure-expired")
    first = _governor(path, owner="worker-a", pressure=pressure)
    first.reserve(request, now_wall=10.0)

    restarted_pressure = _pressure(path)
    restarted = _governor(
        path,
        owner="worker-a",
        pressure=restarted_pressure,
    )

    with pytest.raises(
        CostGovernorConflict,
        match="shared pressure lease is no longer active",
    ):
        restarted.reserve(request, now_wall=100.0)

    # Lookup reaps the expired lease. Recovery does not reacquire authority.
    snap = restarted_pressure.snapshot(
        "ai-runtime",
        tenant_id="tenant-a",
        now=100.0,
    )
    assert snap.active == 0
    # Spend reservation remains fenced for explicit recovery handling.
    assert restarted.runtime.quota_ledger.snapshot("tenant-a")[
        "active_reservations"
    ] == 1


def test_shared_pressure_journal_tamper_is_rejected(
    tmp_path,
) -> None:
    path = tmp_path / "runtime.sqlite3"
    pressure = _configure_pressure(path)
    request = _request("op-pressure-tamper")
    first = _governor(path, owner="worker-a", pressure=pressure)
    first.reserve(request, now_wall=10.0)

    with sqlite3.connect(path) as conn:
        row = conn.execute(
            """
            SELECT runtime_lease_json
            FROM cost_governor_journal
            WHERE operation_id = ?
            """,
            (request.operation_id,),
        ).fetchone()
        assert row is not None
        payload = json.loads(row[0])
        payload["shared_pressure_lease"]["owner_id"] = "worker-b"
        conn.execute(
            """
            UPDATE cost_governor_journal
            SET runtime_lease_json = ?
            WHERE operation_id = ?
            """,
            (
                json.dumps(
                    payload,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                request.operation_id,
            ),
        )

    restarted = _governor(
        path,
        owner="worker-a",
        pressure=_pressure(path),
    )
    with pytest.raises(
        CostGovernorConflict,
        match="shared pressure lease identity does not match runtime",
    ):
        restarted.reserve(request, now_wall=20.0)

    assert restarted.runtime.quota_ledger.snapshot("tenant-a")[
        "active_reservations"
    ] == 1


def test_shared_pressure_ledger_mismatch_rejects_exact_journal(
    tmp_path,
) -> None:
    path = tmp_path / "runtime.sqlite3"
    pressure = _configure_pressure(path)
    request = _request("op-pressure-ledger-mismatch")
    first = _governor(path, owner="worker-a", pressure=pressure)
    first.reserve(request, now_wall=10.0)

    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            UPDATE shared_pressure_lease
            SET owner_id = ?
            WHERE scope = ? AND operation_id = ?
            """,
            ("worker-x", "ai-runtime", request.operation_id),
        )

    restarted = _governor(
        path,
        owner="worker-a",
        pressure=_pressure(path),
    )
    with pytest.raises(
        CostGovernorConflict,
        match="does not match journal",
    ):
        restarted.reserve(request, now_wall=20.0)

    assert restarted.runtime.quota_ledger.snapshot("tenant-a")[
        "active_reservations"
    ] == 1


def test_shared_pressure_journal_requires_pressure_runtime_on_restart(
    tmp_path,
) -> None:
    path = tmp_path / "runtime.sqlite3"
    pressure = _configure_pressure(path)
    request = _request("op-pressure-runtime-missing")
    first = _governor(path, owner="worker-a", pressure=pressure)
    first.reserve(request, now_wall=10.0)

    restarted = _governor(path, owner="unused", pressure=None)
    with pytest.raises(
        CostGovernorError,
        match="requires shared pressure ledger",
    ):
        restarted.reserve(request, now_wall=20.0)

    assert restarted.runtime.quota_ledger.snapshot("tenant-a")[
        "active_reservations"
    ] == 1


def test_live_pressure_lookup_is_read_only_except_expiry_reap(
    tmp_path,
) -> None:
    path = tmp_path / "pressure.sqlite3"
    pressure = _configure_pressure(path)
    lease = pressure.acquire(
        "ai-runtime",
        "tenant-a",
        "op-pressure-lookup",
        "worker-a",
        priority=25,
        lease_seconds=60.0,
        now=10.0,
    )

    assert pressure.lease_for_operation(
        "ai-runtime",
        "op-pressure-lookup",
        now=20.0,
    ) == lease
    assert pressure.snapshot(
        "ai-runtime",
        tenant_id="tenant-a",
        now=20.0,
    ).active == 1

    assert pressure.lease_for_operation(
        "ai-runtime",
        "op-pressure-lookup",
        now=100.0,
    ) is None
    assert pressure.snapshot(
        "ai-runtime",
        tenant_id="tenant-a",
        now=100.0,
    ).active == 0

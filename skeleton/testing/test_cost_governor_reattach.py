from __future__ import annotations

import json
import sqlite3

import pytest

from skeleton.ai.runtime.observability.cost_governor import (
    CostGovernor,
    CostGovernorConflict,
    CostGovernorError,
    SafeCostFallback,
)
from skeleton.intelligence.admission import (
    AdmissionRequest,
    ResourceBudget,
    UsageEstimate,
)
from skeleton.intelligence.admission_runtime import (
    AdmissionRuntime,
    AdmissionRuntimeError,
)
from skeleton.intelligence.quota import TenantQuota, TenantQuotaLedger
from skeleton.intelligence.quota_sqlite import SqliteTenantQuotaLedger


def _quota() -> TenantQuota:
    return TenantQuota(
        window_id="reattach-window",
        max_operations=100,
        max_input_tokens=100_000,
        max_output_tokens=100_000,
        max_cost_usd=100.0,
        max_tool_calls=100,
        max_artifact_bytes=10_000_000,
        max_storage_bytes=10_000_000,
        max_concurrent_operations=8,
    )


def _budget(*, max_concurrency: int = 1, max_cost_usd: float = 5.0) -> ResourceBudget:
    return ResourceBudget(
        max_input_tokens=10_000,
        max_output_tokens=5_000,
        max_cost_usd=max_cost_usd,
        max_wall_seconds=60.0,
        max_provider_attempts=4,
        max_tool_calls=20,
        max_artifact_bytes=1_000_000,
        max_storage_bytes=1_000_000,
        max_concurrency=max_concurrency,
        max_queue_depth=100,
    )


def _request(
    operation_id: str,
    *,
    cost_usd: float = 0.5,
    max_cost_usd: float = 5.0,
    max_concurrency: int = 1,
) -> AdmissionRequest:
    return AdmissionRequest(
        operation_id=operation_id,
        tenant_id="tenant-a",
        capability="model-inference",
        budget=_budget(
            max_concurrency=max_concurrency,
            max_cost_usd=max_cost_usd,
        ),
        estimate=UsageEstimate(
            input_tokens=100,
            output_tokens=20,
            cost_usd=cost_usd,
            wall_seconds=2.0,
            provider_attempts=1,
        ),
    )


def _governor(path) -> CostGovernor:
    return CostGovernor.durable(
        path,
        default_tenant_quota=_quota(),
    )


def test_two_process_reservations_reattach_independent_of_restart_order(
    tmp_path,
) -> None:
    path = tmp_path / "quota.sqlite3"
    request_a = _request("op-a", cost_usd=0.4, max_concurrency=1)
    request_b = _request("op-b", cost_usd=0.6, max_concurrency=1)

    # Each operation was originally admitted in its own process, where local
    # pressure was zero. The durable tenant quota legitimately owns both.
    process_a = _governor(path)
    receipt_a = process_a.reserve(request_a, now_wall=10.0)

    process_b = _governor(path)
    receipt_b = process_b.reserve(request_b, now_wall=11.0)

    before = process_b.runtime.quota_ledger.snapshot("tenant-a")
    assert before["active_reservations"] == 2
    assert before["reserved"]["cost_usd"] == pytest.approx(1.0)

    restarted = _governor(path)
    assert restarted.reserve(request_b, now_wall=20.0) == receipt_b

    # A fresh admit here would see one local active operation and fail the
    # request's max_concurrency=1 boundary. Reattach must not re-admit it.
    assert restarted.reserve(request_a, now_wall=21.0) == receipt_a

    assert restarted.active_reservations() == ("op-a", "op-b")
    after = restarted.runtime.quota_ledger.snapshot("tenant-a")
    assert after["active_reservations"] == 2
    assert after["reserved"]["cost_usd"] == pytest.approx(1.0)
    assert restarted.runtime.telemetry_snapshot()["metrics"]["counters"][
        "admission.reattached_total"
    ] == 2


def test_reattach_preserves_original_receipt_identity(tmp_path) -> None:
    path = tmp_path / "quota.sqlite3"
    request = _request("op-receipt")
    first = _governor(path)

    original = first.reserve(request, now_wall=10.0)
    restarted = _governor(path)
    replay = restarted.reserve(request, now_wall=999.0)

    assert replay == original
    assert replay.lease_id == original.lease_id
    assert replay.admission_decision_id == original.admission_decision_id
    assert replay.quota_reservation_digest == original.quota_reservation_digest


def test_missing_durable_reservation_blocks_reattach_without_re_reserving(
    tmp_path,
) -> None:
    path = tmp_path / "quota.sqlite3"
    request = _request("op-reservation-lost")
    first = _governor(path)
    first.reserve(request, now_wall=10.0)

    # Simulate durable reservation loss outside the governor journal.
    first.runtime.release(request.operation_id)
    assert first.runtime.quota_ledger.snapshot("tenant-a")[
        "active_reservations"
    ] == 0

    restarted = _governor(path)
    with pytest.raises(
        CostGovernorConflict,
        match="no longer active",
    ):
        restarted.reserve(request, now_wall=20.0)

    # Recovery must not turn the missing reservation into a new charge.
    assert restarted.runtime.quota_ledger.snapshot("tenant-a")[
        "active_reservations"
    ] == 0


def test_legacy_active_journal_without_runtime_lease_fails_closed(
    tmp_path,
) -> None:
    path = tmp_path / "quota.sqlite3"
    request = _request("op-legacy-active")
    first = _governor(path)
    first.reserve(request, now_wall=10.0)

    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            UPDATE cost_governor_journal
            SET runtime_lease_json = NULL
            WHERE operation_id = ?
            """,
            (request.operation_id,),
        )

    restarted = _governor(path)
    with pytest.raises(
        CostGovernorError,
        match="legacy active cost journal lacks runtime lease recovery metadata",
    ):
        restarted.reserve(request, now_wall=20.0)

    assert restarted.runtime.quota_ledger.snapshot("tenant-a")[
        "active_reservations"
    ] == 1


def test_fallback_reservation_reattaches_only_with_original_fallback(
    tmp_path,
) -> None:
    path = tmp_path / "quota.sqlite3"
    request = _request(
        "op-fallback",
        cost_usd=1.0,
        max_cost_usd=0.5,
    )
    fallback = SafeCostFallback(
        fallback_id="cheap-model-v1",
        capability="model-inference-cheap",
        estimate=UsageEstimate(
            input_tokens=80,
            output_tokens=20,
            cost_usd=0.2,
            wall_seconds=2.0,
            provider_attempts=1,
        ),
        allowed_failure_reasons=("cost_budget_exceeded",),
    )
    first = _governor(path)
    original = first.reserve(
        request,
        fallback=fallback,
        now_wall=10.0,
    )
    assert original.fallback_used is True

    restarted = _governor(path)
    with pytest.raises(
        CostGovernorConflict,
        match="requires original fallback",
    ):
        restarted.reserve(request, now_wall=20.0)

    replay = restarted.reserve(
        request,
        fallback=fallback,
        now_wall=21.0,
    )
    assert replay == original


def test_changed_fallback_identity_is_rejected_without_mutating_quota(
    tmp_path,
) -> None:
    path = tmp_path / "quota.sqlite3"
    request = _request(
        "op-fallback-conflict",
        cost_usd=1.0,
        max_cost_usd=0.5,
    )
    fallback = SafeCostFallback(
        fallback_id="cheap-model-v1",
        capability="model-inference-cheap",
        estimate=UsageEstimate(
            input_tokens=80,
            output_tokens=20,
            cost_usd=0.2,
            wall_seconds=2.0,
            provider_attempts=1,
        ),
        allowed_failure_reasons=("cost_budget_exceeded",),
    )
    first = _governor(path)
    first.reserve(request, fallback=fallback, now_wall=10.0)

    changed = SafeCostFallback(
        fallback_id="cheap-model-v2",
        capability="model-inference-cheap",
        estimate=fallback.estimate,
        allowed_failure_reasons=fallback.allowed_failure_reasons,
    )
    restarted = _governor(path)
    with pytest.raises(
        CostGovernorConflict,
        match="fallback identity does not match",
    ):
        restarted.reserve(
            request,
            fallback=changed,
            now_wall=20.0,
        )

    snapshot = restarted.runtime.quota_ledger.snapshot("tenant-a")
    assert snapshot["active_reservations"] == 1
    assert snapshot["completions"] == 0


@pytest.mark.parametrize("durable", [False, True])
def test_quota_ledgers_expose_non_mutating_reservation_lookup(
    tmp_path,
    durable,
) -> None:
    if durable:
        ledger = SqliteTenantQuotaLedger(tmp_path / "lookup.sqlite3")
    else:
        ledger = TenantQuotaLedger()
    ledger.configure("tenant-a", _quota())
    request = _request("op-lookup")
    reservation = ledger.reserve(
        request.tenant_id,
        request.operation_id,
        request.estimate,
        now=10.0,
    )

    assert (
        ledger.reservation_for_operation(
            request.tenant_id,
            request.operation_id,
        )
        == reservation
    )
    assert (
        ledger.reservation_for_operation(
            request.tenant_id,
            "missing-operation",
        )
        is None
    )
    assert ledger.snapshot("tenant-a")["active_reservations"] == 1


def test_runtime_reattach_refuses_shared_pressure_without_lease_metadata(
    tmp_path,
) -> None:
    path = tmp_path / "quota.sqlite3"
    request = _request("op-shared-pressure")
    first = _governor(path)
    first.reserve(request, now_wall=10.0)
    active = first.runtime._active[request.operation_id]

    runtime = AdmissionRuntime(
        quota_ledger=SqliteTenantQuotaLedger(path),
        shared_pressure_ledger=object(),  # type: ignore[arg-type]
        shared_pressure_scope="scope-a",
        shared_pressure_owner_id="owner-a",
    )
    with pytest.raises(
        AdmissionRuntimeError,
        match="shared_pressure_reattach_requires_durable_lease_metadata",
    ):
        runtime.reattach(request, active.lease)


def test_runtime_reattach_is_idempotent_for_same_exact_lease(tmp_path) -> None:
    path = tmp_path / "quota.sqlite3"
    request = _request("op-runtime-idempotent")
    first = _governor(path)
    first.reserve(request, now_wall=10.0)
    lease = first.runtime._active[request.operation_id].lease

    runtime = AdmissionRuntime(
        quota_ledger=SqliteTenantQuotaLedger(path),
    )
    first_attach = runtime.reattach(request, lease)
    second_attach = runtime.reattach(request, lease)

    assert first_attach == lease
    assert second_attach == lease
    assert runtime.snapshot()["active_operations"] == (
        request.operation_id,
    )
    assert runtime.telemetry_snapshot()["metrics"]["counters"][
        "admission.reattached_total"
    ] == 1


def test_tampered_runtime_lease_budget_is_rejected_without_quota_mutation(
    tmp_path,
) -> None:
    path = tmp_path / "quota.sqlite3"
    request = _request("op-tampered-remaining")
    first = _governor(path)
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
        payload["remaining"]["cost_usd"] = 999.0
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

    restarted = _governor(path)
    with pytest.raises(
        CostGovernorConflict,
        match="remaining budget does not match request",
    ):
        restarted.reserve(request, now_wall=20.0)

    snapshot = restarted.runtime.quota_ledger.snapshot("tenant-a")
    assert snapshot["active_reservations"] == 1
    assert snapshot["completions"] == 0


def test_tampered_runtime_lease_reason_is_rejected_without_quota_mutation(
    tmp_path,
) -> None:
    path = tmp_path / "quota.sqlite3"
    request = _request("op-tampered-reason")
    first = _governor(path)
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
        payload["reason_code"] = "cost_budget_exceeded"
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

    restarted = _governor(path)
    with pytest.raises(
        CostGovernorConflict,
        match="admission reason is invalid",
    ):
        restarted.reserve(request, now_wall=20.0)

    snapshot = restarted.runtime.quota_ledger.snapshot("tenant-a")
    assert snapshot["active_reservations"] == 1
    assert snapshot["completions"] == 0


@pytest.mark.parametrize(
    ("field", "tampered"),
    [
        ("concurrency", 2),
        ("queue_depth", 99),
    ],
)
def test_tampered_runtime_lease_pressure_breaks_decision_identity(
    tmp_path,
    field,
    tampered,
) -> None:
    path = tmp_path / "quota.sqlite3"
    request = _request(
        "op-tampered-pressure-" + field,
        max_concurrency=3,
    )
    first = _governor(path)
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
        payload["remaining"][field] = tampered
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

    restarted = _governor(path)
    with pytest.raises(
        CostGovernorConflict,
        match="decision identity is invalid",
    ):
        restarted.reserve(request, now_wall=20.0)

    snapshot = restarted.runtime.quota_ledger.snapshot("tenant-a")
    assert snapshot["active_reservations"] == 1
    assert snapshot["completions"] == 0

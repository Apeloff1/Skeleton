from __future__ import annotations

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
from skeleton.intelligence.quota import TenantQuota
from skeleton.intelligence.shared_pressure import (
    SharedPressurePolicy,
    SqliteSharedPressureLedger,
)


_SCOPE = "admission-intent-recovery"
_OWNER = "worker-a"


def _quota() -> TenantQuota:
    return TenantQuota(
        window_id="admission-intent",
        max_operations=100,
        max_input_tokens=100_000,
        max_output_tokens=100_000,
        max_cost_usd=100.0,
        max_tool_calls=100,
        max_artifact_bytes=10_000_000,
        max_storage_bytes=10_000_000,
        max_concurrent_operations=8,
    )


def _request(
    operation_id: str,
    *,
    cost_usd: float = 0.5,
    max_cost_usd: float = 5.0,
    deadline_monotonic: float | None = None,
) -> AdmissionRequest:
    return AdmissionRequest(
        operation_id=operation_id,
        tenant_id="tenant-a",
        capability="model-inference",
        budget=ResourceBudget(
            max_input_tokens=10_000,
            max_output_tokens=5_000,
            max_cost_usd=max_cost_usd,
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
            cost_usd=cost_usd,
            wall_seconds=2.0,
            provider_attempts=1,
        ),
        priority=7,
        deadline_monotonic=deadline_monotonic,
    )


def _pressure(path) -> SqliteSharedPressureLedger:
    ledger = SqliteSharedPressureLedger(path)
    try:
        ledger.configure(
            SharedPressurePolicy(
                scope=_SCOPE,
                max_concurrency=4,
                max_queue_depth=100,
                max_tenant_concurrency=4,
                max_tenant_queue_depth=100,
                soft_shed_fraction=1.0,
                protect_priority_at_or_below=10,
                default_lease_seconds=60.0,
            )
        )
    except Exception:
        pass
    return ledger


def _governor(
    quota_path,
    pressure_path=None,
) -> CostGovernor:
    kwargs = {}
    if pressure_path is not None:
        kwargs = {
            "shared_pressure_ledger": _pressure(pressure_path),
            "shared_pressure_scope": _SCOPE,
            "shared_pressure_owner_id": _OWNER,
        }
    return CostGovernor.durable(
        quota_path,
        default_tenant_quota=_quota(),
        **kwargs,
    )


def _fallback() -> SafeCostFallback:
    return SafeCostFallback(
        fallback_id="cheap-model-v1",
        capability="model-inference-cheap",
        estimate=UsageEstimate(
            input_tokens=80,
            output_tokens=15,
            cost_usd=0.2,
            wall_seconds=1.5,
            provider_attempts=1,
        ),
        allowed_failure_reasons=("cost_budget_exceeded",),
    )


def _intent_count(path) -> int:
    with sqlite3.connect(path) as conn:
        return int(
            conn.execute(
                "SELECT COUNT(*) FROM cost_governor_admission_intent"
            ).fetchone()[0]
        )


def test_crash_after_decision_before_allocation_retries_cleanly(
    tmp_path,
    monkeypatch,
) -> None:
    quota_path = tmp_path / "quota.sqlite3"
    pressure_path = tmp_path / "pressure.sqlite3"
    request = _request("op-before-allocation")
    first = _governor(quota_path, pressure_path)

    pressure = first.runtime.shared_pressure_ledger
    assert pressure is not None

    def crash_before_acquire(*_args, **_kwargs):
        raise SystemExit("crash after decision persistence")

    monkeypatch.setattr(pressure, "acquire", crash_before_acquire)

    with pytest.raises(SystemExit):
        first.reserve(
            request,
            now_monotonic=10.0,
            now_wall=10.0,
        )

    assert _intent_count(quota_path) == 1
    assert first.runtime.quota_ledger.snapshot("tenant-a")[
        "active_reservations"
    ] == 0

    restarted = _governor(quota_path, pressure_path)
    receipt = restarted.reserve(
        request,
        now_monotonic=20.0,
        now_wall=20.0,
    )

    assert receipt.operation_id == request.operation_id
    assert _intent_count(quota_path) == 0
    assert restarted.runtime.quota_ledger.snapshot("tenant-a")[
        "active_reservations"
    ] == 1
    assert _pressure(pressure_path).snapshot(
        _SCOPE,
        tenant_id="tenant-a",
        now=20.5,
    ).active == 1


def test_crash_after_shared_pressure_before_quota_releases_orphan_then_retries(
    tmp_path,
    monkeypatch,
) -> None:
    quota_path = tmp_path / "quota.sqlite3"
    pressure_path = tmp_path / "pressure.sqlite3"
    request = _request("op-after-shared")
    first = _governor(quota_path, pressure_path)

    def crash_before_quota(*_args, **_kwargs):
        raise SystemExit("crash after shared pressure allocation")

    monkeypatch.setattr(
        first.runtime.quota_ledger,
        "reserve",
        crash_before_quota,
    )

    with pytest.raises(SystemExit):
        first.reserve(
            request,
            now_monotonic=10.0,
            now_wall=10.0,
        )

    assert _pressure(pressure_path).snapshot(
        _SCOPE,
        tenant_id="tenant-a",
        now=10.5,
    ).active == 1
    assert _intent_count(quota_path) == 1

    restarted = _governor(quota_path, pressure_path)
    restarted.reserve(
        request,
        now_monotonic=20.0,
        now_wall=20.0,
    )

    assert _intent_count(quota_path) == 0
    assert restarted.runtime.quota_ledger.snapshot("tenant-a")[
        "active_reservations"
    ] == 1
    # The orphan was settled before one fresh lease was acquired.
    assert _pressure(pressure_path).snapshot(
        _SCOPE,
        tenant_id="tenant-a",
        now=20.5,
    ).active == 1


def test_crash_after_quota_before_active_journal_recovers_exact_lease(
    tmp_path,
    monkeypatch,
) -> None:
    quota_path = tmp_path / "quota.sqlite3"
    pressure_path = tmp_path / "pressure.sqlite3"
    request = _request("op-after-quota")
    first = _governor(quota_path, pressure_path)
    assert first._journal is not None

    def crash_before_active(*_args, **_kwargs):
        raise SystemExit("crash before active cost journal")

    monkeypatch.setattr(
        first._journal,
        "record_active",
        crash_before_active,
    )

    with pytest.raises(SystemExit):
        first.reserve(
            request,
            now_monotonic=10.0,
            now_wall=10.0,
        )

    assert _intent_count(quota_path) == 1
    assert first.runtime.quota_ledger.snapshot("tenant-a")[
        "active_reservations"
    ] == 1
    assert _pressure(pressure_path).snapshot(
        _SCOPE,
        tenant_id="tenant-a",
        now=10.5,
    ).active == 1

    restarted = _governor(quota_path, pressure_path)
    recovered = restarted.reserve(
        request,
        now_monotonic=999.0,
        now_wall=20.0,
    )

    assert recovered.operation_id == request.operation_id
    assert _intent_count(quota_path) == 0
    assert restarted.runtime.telemetry_snapshot()["metrics"]["counters"][
        "admission.reattached_total"
    ] == 1
    assert restarted.runtime.quota_ledger.snapshot("tenant-a")[
        "active_reservations"
    ] == 1
    assert _pressure(pressure_path).snapshot(
        _SCOPE,
        tenant_id="tenant-a",
        now=20.5,
    ).active == 1


def test_crash_after_active_journal_before_intent_clear_is_idempotent(
    tmp_path,
    monkeypatch,
) -> None:
    quota_path = tmp_path / "quota.sqlite3"
    request = _request("op-after-active")
    first = _governor(quota_path)
    assert first._journal is not None

    original_clear = first._journal.clear_admission_intent

    def crash_on_clear(_operation_id: str) -> None:
        raise SystemExit("crash after active journal commit")

    monkeypatch.setattr(
        first._journal,
        "clear_admission_intent",
        crash_on_clear,
    )

    with pytest.raises(SystemExit):
        first.reserve(
            request,
            now_monotonic=10.0,
            now_wall=10.0,
        )

    assert _intent_count(quota_path) == 1
    monkeypatch.setattr(
        first._journal,
        "clear_admission_intent",
        original_clear,
    )

    restarted = _governor(quota_path)
    receipt = restarted.reserve(
        request,
        now_monotonic=20.0,
        now_wall=20.0,
    )

    assert receipt.operation_id == request.operation_id
    assert _intent_count(quota_path) == 0
    assert restarted.runtime.quota_ledger.snapshot("tenant-a")[
        "active_reservations"
    ] == 1


def test_recovery_does_not_reevaluate_expired_deadline(
    tmp_path,
    monkeypatch,
) -> None:
    quota_path = tmp_path / "quota.sqlite3"
    pressure_path = tmp_path / "pressure.sqlite3"
    request = _request(
        "op-deadline-recovery",
        deadline_monotonic=50.0,
    )
    first = _governor(quota_path, pressure_path)
    assert first._journal is not None

    monkeypatch.setattr(
        first._journal,
        "record_active",
        lambda **_kwargs: (_ for _ in ()).throw(
            SystemExit("crash after admitted durable allocation")
        ),
    )

    with pytest.raises(SystemExit):
        first.reserve(
            request,
            now_monotonic=10.0,
            now_wall=10.0,
        )

    restarted = _governor(quota_path, pressure_path)
    receipt = restarted.reserve(
        request,
        now_monotonic=100.0,
        now_wall=20.0,
    )

    assert receipt.operation_id == request.operation_id
    assert restarted.runtime.telemetry_snapshot()["metrics"]["counters"][
        "admission.reattached_total"
    ] == 1


def test_fallback_admission_recovers_original_fallback_identity(
    tmp_path,
    monkeypatch,
) -> None:
    quota_path = tmp_path / "quota.sqlite3"
    pressure_path = tmp_path / "pressure.sqlite3"
    request = _request(
        "op-fallback-intent",
        cost_usd=1.0,
        max_cost_usd=0.5,
    )
    fallback = _fallback()
    first = _governor(quota_path, pressure_path)
    assert first._journal is not None

    monkeypatch.setattr(
        first._journal,
        "record_active",
        lambda **_kwargs: (_ for _ in ()).throw(
            SystemExit("crash after fallback allocation")
        ),
    )

    with pytest.raises(SystemExit):
        first.reserve(
            request,
            fallback=fallback,
            now_monotonic=10.0,
            now_wall=10.0,
        )

    restarted = _governor(quota_path, pressure_path)
    with pytest.raises(
        CostGovernorConflict,
        match="requires original fallback",
    ):
        restarted.reserve(
            request,
            now_monotonic=20.0,
            now_wall=20.0,
        )

    receipt = restarted.reserve(
        request,
        fallback=fallback,
        now_monotonic=20.0,
        now_wall=20.0,
    )
    assert receipt.fallback_used is True
    assert receipt.fallback_id == fallback.fallback_id
    assert receipt.selected_capability == fallback.capability
    assert _intent_count(quota_path) == 0


def test_changed_request_cannot_claim_crashed_admission_intent(
    tmp_path,
    monkeypatch,
) -> None:
    quota_path = tmp_path / "quota.sqlite3"
    request = _request("op-intent-request-conflict")
    first = _governor(quota_path)
    assert first._journal is not None
    monkeypatch.setattr(
        first._journal,
        "record_active",
        lambda **_kwargs: (_ for _ in ()).throw(
            SystemExit("crash after quota allocation")
        ),
    )

    with pytest.raises(SystemExit):
        first.reserve(request, now_wall=10.0)

    changed = _request(
        request.operation_id,
        cost_usd=0.6,
    )
    restarted = _governor(quota_path)
    with pytest.raises(
        CostGovernorConflict,
        match="requested inputs do not match replay",
    ):
        restarted.reserve(changed, now_wall=20.0)

    assert restarted.runtime.quota_ledger.snapshot("tenant-a")[
        "active_reservations"
    ] == 1


def test_tampered_admission_decision_intent_fails_closed(
    tmp_path,
    monkeypatch,
) -> None:
    quota_path = tmp_path / "quota.sqlite3"
    request = _request("op-intent-tampered")
    first = _governor(quota_path)
    assert first._journal is not None
    monkeypatch.setattr(
        first._journal,
        "record_active",
        lambda **_kwargs: (_ for _ in ()).throw(
            SystemExit("crash after quota allocation")
        ),
    )

    with pytest.raises(SystemExit):
        first.reserve(request, now_wall=10.0)

    with sqlite3.connect(quota_path) as conn:
        row = conn.execute(
            """
            SELECT payload_json
            FROM cost_governor_admission_intent
            WHERE operation_id = ?
            """,
            (request.operation_id,),
        ).fetchone()
        assert row is not None
        import json

        payload = json.loads(row[0])
        payload["remaining"]["concurrency"] -= 1
        conn.execute(
            """
            UPDATE cost_governor_admission_intent
            SET payload_json = ?
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

    restarted = _governor(quota_path)
    with pytest.raises(
        CostGovernorConflict,
        match="decision identity is invalid",
    ):
        restarted.reserve(request, now_wall=20.0)

    assert restarted.runtime.quota_ledger.snapshot("tenant-a")[
        "active_reservations"
    ] == 1


def test_decision_persistence_failure_allocates_no_authority(
    tmp_path,
    monkeypatch,
) -> None:
    quota_path = tmp_path / "quota.sqlite3"
    pressure_path = tmp_path / "pressure.sqlite3"
    request = _request("op-intent-write-failure")
    governor = _governor(quota_path, pressure_path)
    assert governor._journal is not None

    def reject_decision(*_args, **_kwargs):
        raise RuntimeError("simulated durable intent write failure")

    monkeypatch.setattr(
        governor._journal,
        "record_admission_decision",
        reject_decision,
    )

    with pytest.raises(
        CostGovernorError,
        match="admission_decision_persistence_failed",
    ):
        governor.reserve(
            request,
            now_monotonic=10.0,
            now_wall=10.0,
        )

    assert governor.runtime.quota_ledger.snapshot("tenant-a")[
        "active_reservations"
    ] == 0
    assert _pressure(pressure_path).snapshot(
        _SCOPE,
        tenant_id="tenant-a",
        now=10.5,
    ).active == 0
    assert _intent_count(quota_path) == 1


def test_successful_reserve_clears_admission_intent(
    tmp_path,
) -> None:
    quota_path = tmp_path / "quota.sqlite3"
    pressure_path = tmp_path / "pressure.sqlite3"
    request = _request("op-intent-clean-success")
    governor = _governor(quota_path, pressure_path)

    receipt = governor.reserve(
        request,
        now_monotonic=10.0,
        now_wall=10.0,
    )

    assert receipt.operation_id == request.operation_id
    assert _intent_count(quota_path) == 0
    assert governor.runtime.quota_ledger.snapshot("tenant-a")[
        "active_reservations"
    ] == 1
    assert _pressure(pressure_path).snapshot(
        _SCOPE,
        tenant_id="tenant-a",
        now=10.5,
    ).active == 1


def test_unjournaled_quota_authority_cannot_be_adopted(
    tmp_path,
) -> None:
    quota_path = tmp_path / "quota.sqlite3"
    request = _request("op-orphan-quota")
    governor = _governor(quota_path)
    ledger = governor.runtime.quota_ledger
    ledger.configure("tenant-a", _quota())
    original = ledger.reserve(
        request.tenant_id,
        request.operation_id,
        request.estimate,
        now=10.0,
    )

    with pytest.raises(
        CostGovernorConflict,
        match="unjournaled durable quota authority already exists",
    ):
        governor.reserve(
            request,
            now_monotonic=20.0,
            now_wall=20.0,
        )

    recovered = ledger.reservation_for_operation(
        request.tenant_id,
        request.operation_id,
    )
    assert recovered == original
    assert _intent_count(quota_path) == 0


def test_unjournaled_shared_pressure_authority_cannot_be_adopted(
    tmp_path,
) -> None:
    quota_path = tmp_path / "quota.sqlite3"
    pressure_path = tmp_path / "pressure.sqlite3"
    request = _request("op-orphan-pressure")
    pressure = _pressure(pressure_path)
    lease = pressure.acquire(
        _SCOPE,
        request.tenant_id,
        request.operation_id,
        _OWNER,
        priority=request.priority,
        lease_seconds=60.0,
        now=10.0,
    )
    governor = _governor(quota_path, pressure_path)

    with pytest.raises(
        CostGovernorConflict,
        match="unjournaled shared pressure authority already exists",
    ):
        governor.reserve(
            request,
            now_monotonic=20.0,
            now_wall=20.0,
        )

    assert pressure.lease_for_operation(
        _SCOPE,
        request.operation_id,
        now=20.5,
    ) == lease
    assert governor.runtime.quota_ledger.snapshot("tenant-a")[
        "active_reservations"
    ] == 0
    assert _intent_count(quota_path) == 0


def test_extra_admission_intent_budget_field_is_rejected(
    tmp_path,
    monkeypatch,
) -> None:
    quota_path = tmp_path / "quota.sqlite3"
    request = _request("op-intent-extra-field")
    first = _governor(quota_path)
    assert first._journal is not None

    monkeypatch.setattr(
        first._journal,
        "record_active",
        lambda **_kwargs: (_ for _ in ()).throw(
            SystemExit("crash after quota allocation")
        ),
    )
    with pytest.raises(SystemExit):
        first.reserve(request, now_wall=10.0)

    with sqlite3.connect(quota_path) as conn:
        row = conn.execute(
            """
            SELECT payload_json
            FROM cost_governor_admission_intent
            WHERE operation_id = ?
            """,
            (request.operation_id,),
        ).fetchone()
        assert row is not None
        import json

        payload = json.loads(row[0])
        payload["remaining"]["unexpected_dimension"] = 1
        conn.execute(
            """
            UPDATE cost_governor_admission_intent
            SET payload_json = ?
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

    restarted = _governor(quota_path)
    with pytest.raises(
        CostGovernorError,
        match="remaining-budget fields are invalid",
    ):
        restarted.reserve(request, now_wall=20.0)

    assert restarted.runtime.quota_ledger.snapshot("tenant-a")[
        "active_reservations"
    ] == 1


def test_expired_pressure_after_quota_crash_abandons_clean_quota_and_readmits(
    tmp_path,
    monkeypatch,
) -> None:
    quota_path = tmp_path / "quota.sqlite3"
    pressure_path = tmp_path / "pressure.sqlite3"
    request = _request("op-intent-pressure-expired")
    first = _governor(quota_path, pressure_path)
    assert first._journal is not None

    monkeypatch.setattr(
        first._journal,
        "record_active",
        lambda **_kwargs: (_ for _ in ()).throw(
            SystemExit("crash after quota allocation")
        ),
    )
    with pytest.raises(SystemExit):
        first.reserve(
            request,
            now_monotonic=10.0,
            now_wall=10.0,
        )

    # The default admission lease expires at max_wall_seconds=60.
    restarted = _governor(quota_path, pressure_path)
    receipt = restarted.reserve(
        request,
        now_monotonic=80.0,
        now_wall=80.0,
    )

    assert receipt.operation_id == request.operation_id
    assert _intent_count(quota_path) == 0
    snapshot = restarted.runtime.quota_ledger.snapshot("tenant-a")
    assert snapshot["active_reservations"] == 1
    assert snapshot["usage_events"] == 0
    assert _pressure(pressure_path).snapshot(
        _SCOPE,
        tenant_id="tenant-a",
        now=80.5,
    ).active == 1


def test_pressure_loss_cannot_abandon_quota_after_metered_usage(
    tmp_path,
    monkeypatch,
) -> None:
    quota_path = tmp_path / "quota.sqlite3"
    pressure_path = tmp_path / "pressure.sqlite3"
    request = _request("op-intent-pressure-metered")
    first = _governor(quota_path, pressure_path)
    assert first._journal is not None

    monkeypatch.setattr(
        first._journal,
        "record_active",
        lambda **_kwargs: (_ for _ in ()).throw(
            SystemExit("crash after quota allocation")
        ),
    )
    with pytest.raises(SystemExit):
        first.reserve(
            request,
            now_monotonic=10.0,
            now_wall=10.0,
        )

    reservation = first.runtime.quota_ledger.reservation_for_operation(
        request.tenant_id,
        request.operation_id,
    )
    assert reservation is not None
    first.runtime.quota_ledger.record_usage_event(
        reservation.reservation_id,
        "adversarial-prejournal-usage",
        "provider",
        UsageEstimate(
            input_tokens=1,
            output_tokens=1,
            cost_usd=0.01,
        ),
        now=11.0,
    )

    restarted = _governor(quota_path, pressure_path)
    with pytest.raises(
        CostGovernorConflict,
        match="orphan admission quota cannot be safely abandoned",
    ):
        restarted.reserve(
            request,
            now_monotonic=80.0,
            now_wall=80.0,
        )

    snapshot = restarted.runtime.quota_ledger.snapshot("tenant-a")
    assert snapshot["active_reservations"] == 1
    assert snapshot["usage_events"] == 1
    assert _intent_count(quota_path) == 1

def test_undecided_admission_intent_is_immutable_across_racing_writers(
    tmp_path,
) -> None:
    quota_path = tmp_path / "quota.sqlite3"
    governor = _governor(quota_path)
    assert governor._journal is not None

    original = _request("op-intent-race")
    changed = _request(
        original.operation_id,
        cost_usd=0.6,
    )
    original_intent = governor._admission_intent(
        requested=original,
        selected=original,
        fallback=None,
        fallback_reason=None,
    )
    changed_intent = governor._admission_intent(
        requested=changed,
        selected=changed,
        fallback=None,
        fallback_reason=None,
    )

    first = governor._journal.begin_admission_intent(original_intent)
    assert first == original_intent
    assert (
        governor._journal.begin_admission_intent(original_intent)
        == original_intent
    )

    with pytest.raises(
        CostGovernorConflict,
        match="admission intent replayed with different inputs",
    ):
        governor._journal.begin_admission_intent(changed_intent)

    assert (
        governor._journal.load_admission_intent(original.operation_id)
        == original_intent
    )
    assert _intent_count(quota_path) == 1


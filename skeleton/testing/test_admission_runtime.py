from __future__ import annotations

import pytest

from skeleton.intelligence.admission import (
    AdmissionError,
    AdmissionRequest,
    ResourceBudget,
    RuntimePressure,
    UsageEstimate,
)
from skeleton.intelligence.admission_runtime import (
    AdmissionRuntime,
    AdmissionRuntimeConflict,
    AdmissionRuntimeError,
)
from skeleton.intelligence.quota import (
    QuotaConflict,
    TenantQuota,
    TenantQuotaLedger,
)
from skeleton.intelligence.shared_pressure import (
    SharedPressureConflict,
    SharedPressurePolicy,
    SqliteSharedPressureLedger,
)


def _request(
    operation_id: str,
    *,
    tenant_id: str = "tenant-a",
    max_concurrency: int = 2,
    max_queue_depth: int = 5,
    input_tokens: int = 10,
    cost_usd: float = 0.1,
) -> AdmissionRequest:
    return AdmissionRequest(
        operation_id=operation_id,
        tenant_id=tenant_id,
        capability="model-inference",
        budget=ResourceBudget(
            max_input_tokens=1_000,
            max_output_tokens=1_000,
            max_cost_usd=10.0,
            max_wall_seconds=30.0,
            max_provider_attempts=3,
            max_tool_calls=10,
            max_artifact_bytes=1024,
            max_concurrency=max_concurrency,
            max_queue_depth=max_queue_depth,
        ),
        estimate=UsageEstimate(
            input_tokens=input_tokens,
            output_tokens=5,
            cost_usd=cost_usd,
            wall_seconds=1.0,
            provider_attempts=1,
        ),
        # Caller pressure is intentionally ignored by the runtime controller.
        pressure=RuntimePressure(active_operations=999, queue_depth=999),
    )


def _quota_runtime(
    *,
    max_operations: int = 10,
    max_input_tokens: int = 1_000,
    max_cost_usd: float = 10.0,
    max_concurrent_operations: int = 3,
) -> tuple[AdmissionRuntime, TenantQuotaLedger]:
    ledger = TenantQuotaLedger()
    ledger.configure(
        "tenant-a",
        TenantQuota(
            window_id="window-1",
            max_operations=max_operations,
            max_input_tokens=max_input_tokens,
            max_output_tokens=1_000,
            max_cost_usd=max_cost_usd,
            max_tool_calls=100,
            max_artifact_bytes=10_000,
            max_concurrent_operations=max_concurrent_operations,
        ),
    )
    return AdmissionRuntime(quota_ledger=ledger), ledger


def test_runtime_owns_live_pressure_instead_of_trusting_caller_pressure() -> None:
    runtime = AdmissionRuntime()

    first = runtime.admit(_request("op-1"), now_wall=10.0)

    assert first.decision.admitted is True
    assert first.decision.reason_code == "within_budget"
    assert runtime.pressure.active_operations == 1


def test_shared_concurrency_pressure_blocks_next_operation() -> None:
    runtime = AdmissionRuntime()
    runtime.admit(_request("op-1", max_concurrency=1), now_wall=10.0)

    with pytest.raises(AdmissionError, match="concurrency_saturated"):
        runtime.admit(_request("op-2", max_concurrency=1), now_wall=11.0)

    assert runtime.pressure.active_operations == 1


def test_queue_depth_is_shared_and_fail_closed() -> None:
    runtime = AdmissionRuntime()
    runtime.set_queue_depth(2)

    with pytest.raises(AdmissionError, match="queue_saturated"):
        runtime.admit(
            _request("op-1", max_queue_depth=2),
            now_wall=10.0,
        )

    assert runtime.pressure == RuntimePressure(
        active_operations=0,
        queue_depth=2,
    )


def test_duplicate_active_admission_is_idempotent() -> None:
    runtime = AdmissionRuntime()
    request = _request("op-1")

    first = runtime.admit(request, now_wall=10.0)
    second = runtime.admit(request, now_wall=20.0)

    assert first == second
    assert runtime.pressure.active_operations == 1


def test_duplicate_operation_with_different_budget_conflicts() -> None:
    runtime = AdmissionRuntime()
    runtime.admit(_request("op-1", max_concurrency=2), now_wall=10.0)

    with pytest.raises(AdmissionRuntimeConflict, match="different inputs"):
        runtime.admit(
            _request("op-1", max_concurrency=3),
            now_wall=11.0,
        )


def test_tenant_quota_reservation_and_actual_usage_reconciliation() -> None:
    runtime, ledger = _quota_runtime()
    request = _request("op-1", input_tokens=100, cost_usd=1.0)

    lease = runtime.admit(request, now_wall=10.0)
    assert lease.quota_reservation is not None
    reserved = ledger.snapshot("tenant-a")
    assert reserved["reserved"]["input_tokens"] == 100
    assert reserved["active_reservations"] == 1

    completion = runtime.complete(
        "op-1",
        UsageEstimate(
            input_tokens=75,
            output_tokens=4,
            cost_usd=0.5,
            wall_seconds=0.8,
            provider_attempts=1,
        ),
        now_wall=11.0,
    )

    assert completion.quota_completion is not None
    assert completion.quota_completion.actual.input_tokens == 75
    snapshot = ledger.snapshot("tenant-a")
    assert snapshot["active_reservations"] == 0
    assert snapshot["committed"]["input_tokens"] == 75
    assert snapshot["committed"]["cost_usd"] == 0.5
    assert runtime.pressure.active_operations == 0


def test_quota_denial_does_not_consume_runtime_concurrency() -> None:
    runtime, ledger = _quota_runtime(max_input_tokens=50)

    with pytest.raises(AdmissionError, match="tenant_quota_exceeded:input_tokens"):
        runtime.admit(
            _request("op-1", input_tokens=51),
            now_wall=10.0,
        )

    assert runtime.pressure.active_operations == 0
    assert ledger.snapshot("tenant-a")["active_reservations"] == 0


def test_release_returns_quota_and_pressure_capacity() -> None:
    runtime, ledger = _quota_runtime(max_concurrent_operations=1)
    lease = runtime.admit(_request("op-1"), now_wall=10.0)

    released = runtime.release("op-1")

    assert released == lease
    assert runtime.pressure.active_operations == 0
    assert ledger.snapshot("tenant-a")["active_reservations"] == 0
    assert ledger.snapshot("tenant-a")["committed"]["operations"] == 0


def test_complete_unknown_operation_fails_closed() -> None:
    runtime = AdmissionRuntime()

    with pytest.raises(AdmissionRuntimeError, match="no active"):
        runtime.complete("missing", UsageEstimate())


def test_snapshot_exposes_pressure_without_budget_payloads() -> None:
    runtime = AdmissionRuntime()
    runtime.set_queue_depth(3)
    runtime.admit(_request("op-1"), now_wall=10.0)

    snapshot = runtime.snapshot()

    assert snapshot == {
        "pressure": {
            "active_operations": 1,
            "queue_depth": 3,
        },
        "active_operations": ("op-1",),
        "unknown_usage_events": 0,
        "unknown_usage_operations": (),
        "quota_enabled": False,
    }


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1.0])
def test_admit_rejects_invalid_wall_clock(value: float) -> None:
    runtime = AdmissionRuntime()

    with pytest.raises(ValueError, match="finite and non-negative"):
        runtime.admit(_request("op-clock"), now_wall=value)

    assert runtime.pressure.active_operations == 0


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1.0])
def test_complete_rejects_invalid_wall_clock_without_releasing_lease(
    value: float,
) -> None:
    runtime = AdmissionRuntime()
    runtime.admit(_request("op-clock"), now_wall=10.0)

    with pytest.raises(ValueError, match="finite and non-negative"):
        runtime.complete("op-clock", UsageEstimate(), now_wall=value)

    assert runtime.pressure.active_operations == 1


def test_unknown_actual_usage_blocks_terminal_accounting_until_resolved() -> None:
    runtime, ledger = _quota_runtime()
    runtime.admit(_request("op-unknown"), now_wall=10.0)

    marker = runtime.mark_usage_unknown(
        "op-unknown",
        "tool-event-1",
        "tool",
        "provider did not return usage",
        now_wall=10.5,
    )

    assert marker.category == "tool"
    assert ledger.snapshot("tenant-a")["unknown_usage_events"] == 1
    with pytest.raises(AdmissionRuntimeError, match="actual_usage_unknown:tool"):
        runtime.complete("op-unknown", UsageEstimate(), now_wall=11.0)
    with pytest.raises(AdmissionRuntimeError, match="actual_usage_unknown:tool"):
        runtime.release("op-unknown")

    resolved = runtime.resolve_unknown_usage(
        "op-unknown",
        "tool-event-1",
        UsageEstimate(tool_calls=1),
        now_wall=11.5,
    )
    assert resolved.category == "tool"
    assert ledger.snapshot("tenant-a")["unknown_usage_events"] == 0

    completion = runtime.complete(
        "op-unknown",
        UsageEstimate(),
        now_wall=12.0,
    )
    assert completion.quota_completion is not None
    assert completion.quota_completion.actual.tool_calls == 1


def test_incremental_metering_enforces_operation_budget_before_side_effect_growth() -> None:
    runtime, _ = _quota_runtime()
    request = _request("op-meter")
    runtime.admit(request, now_wall=10.0)

    runtime.meter_tool_call("op-meter", "tool-1", now_wall=10.1)
    for index in range(2, 11):
        runtime.meter_tool_call(
            "op-meter",
            f"tool-{index}",
            now_wall=10.0 + index / 10,
        )

    with pytest.raises(AdmissionError, match="operation_budget_exceeded:tool_calls"):
        runtime.meter_tool_call("op-meter", "tool-11", now_wall=12.0)


def test_metered_usage_cannot_be_discarded_by_release() -> None:
    runtime, _ = _quota_runtime()
    runtime.admit(_request("op-metered-release"), now_wall=10.0)
    runtime.meter_artifact_bytes(
        "op-metered-release",
        "artifact-1",
        10,
        now_wall=10.1,
    )

    with pytest.raises(QuotaConflict, match="cannot release reservation after metered usage"):
        runtime.release("op-metered-release")


def test_completion_emits_payload_free_estimate_actual_delta_telemetry() -> None:
    runtime = AdmissionRuntime()
    request = _request(
        "op-telemetry",
        tenant_id="tenant-secret",
        input_tokens=100,
        cost_usd=1.0,
    )

    runtime.admit(request, now_wall=10.0)
    runtime.complete(
        "op-telemetry",
        UsageEstimate(
            input_tokens=80,
            output_tokens=7,
            cost_usd=0.4,
            wall_seconds=0.6,
            provider_attempts=1,
            tool_calls=2,
            artifact_bytes=64,
            storage_bytes=32,
        ),
        now_wall=11.0,
    )

    telemetry = runtime.telemetry_snapshot()
    metrics = telemetry["metrics"]

    assert telemetry["schema_version"] == 1
    assert metrics["counters"]["admission.admitted_total"] == 1
    assert metrics["counters"]["admission.completed_total"] == 1

    assert metrics["samples"]["admission.estimated.input_tokens"] == (100.0,)
    assert metrics["samples"]["admission.actual.input_tokens"] == (80.0,)
    assert metrics["samples"]["admission.delta.input_tokens"] == (-20.0,)

    assert metrics["samples"]["admission.estimated.output_tokens"] == (5.0,)
    assert metrics["samples"]["admission.actual.output_tokens"] == (7.0,)
    assert metrics["samples"]["admission.delta.output_tokens"] == (2.0,)

    assert metrics["samples"]["admission.estimated.cost_usd"] == (1.0,)
    assert metrics["samples"]["admission.actual.cost_usd"] == (0.4,)
    assert metrics["samples"]["admission.delta.cost_usd"] == pytest.approx((-0.6,))

    assert metrics["samples"]["admission.actual.tool_calls"] == (2.0,)
    assert metrics["samples"]["admission.delta.tool_calls"] == (2.0,)
    assert metrics["samples"]["admission.actual.artifact_bytes"] == (64.0,)
    assert metrics["samples"]["admission.delta.artifact_bytes"] == (64.0,)
    assert metrics["samples"]["admission.estimated.storage_bytes"] == (0.0,)
    assert metrics["samples"]["admission.actual.storage_bytes"] == (32.0,)
    assert metrics["samples"]["admission.delta.storage_bytes"] == (32.0,)

    serialized = repr(telemetry)
    assert "op-telemetry" not in serialized
    assert "tenant-secret" not in serialized


def test_idempotent_replay_does_not_double_count_admission_telemetry() -> None:
    runtime = AdmissionRuntime()
    request = _request("op-telemetry-replay")

    first = runtime.admit(request, now_wall=10.0)
    second = runtime.admit(request, now_wall=11.0)

    assert second == first
    telemetry = runtime.telemetry_snapshot()["metrics"]
    assert telemetry["counters"]["admission.admitted_total"] == 1
    assert telemetry["samples"]["admission.estimated.input_tokens"] == (10.0,)

def _shared_pressure_runtime(
    path,
    *,
    owner_id: str,
    quota_ledger: TenantQuotaLedger | None = None,
) -> AdmissionRuntime:
    pressure = SqliteSharedPressureLedger(path)
    try:
        pressure.configure(
            SharedPressurePolicy(
                scope="ai-work",
                max_concurrency=1,
                max_queue_depth=8,
                max_tenant_concurrency=1,
                max_tenant_queue_depth=4,
                soft_shed_fraction=1.0,
                protect_priority_at_or_below=100,
                default_lease_seconds=30.0,
            )
        )
    except SharedPressureConflict:
        pass
    return AdmissionRuntime(
        quota_ledger=quota_ledger,
        shared_pressure_ledger=pressure,
        shared_pressure_scope="ai-work",
        shared_pressure_owner_id=owner_id,
    )


def test_shared_pressure_prevents_cross_worker_overbooking(tmp_path) -> None:
    path = tmp_path / "pressure.sqlite3"
    first = _shared_pressure_runtime(path, owner_id="worker-a")
    second = _shared_pressure_runtime(path, owner_id="worker-b")

    first.admit(_request("op-a", max_concurrency=2), now_wall=10.0)

    with pytest.raises(AdmissionError, match="shared_concurrency_saturated"):
        second.admit(
            _request(
                "op-b",
                tenant_id="tenant-b",
                max_concurrency=2,
            ),
            now_wall=10.1,
        )

    assert first.pressure.active_operations == 1
    assert second.pressure.active_operations == 0

    first.complete(
        "op-a",
        UsageEstimate(),
        now_wall=10.2,
    )
    admitted = second.admit(
        _request(
            "op-b",
            tenant_id="tenant-b",
            max_concurrency=2,
        ),
        now_wall=10.3,
    )
    assert admitted.operation_id == "op-b"


def test_quota_denial_releases_shared_pressure_slot(tmp_path) -> None:
    path = tmp_path / "pressure.sqlite3"
    ledger = TenantQuotaLedger()
    ledger.configure(
        "tenant-a",
        TenantQuota(
            window_id="window-shared",
            max_operations=10,
            max_input_tokens=5,
            max_output_tokens=1_000,
            max_cost_usd=10.0,
            max_tool_calls=100,
            max_artifact_bytes=10_000,
            max_storage_bytes=10_000,
            max_concurrent_operations=4,
        ),
    )
    runtime = _shared_pressure_runtime(
        path,
        owner_id="worker-a",
        quota_ledger=ledger,
    )

    with pytest.raises(
        AdmissionError,
        match="tenant_quota_exceeded:input_tokens",
    ):
        runtime.admit(
            _request("op-denied", input_tokens=10),
            now_wall=20.0,
        )

    pressure = SqliteSharedPressureLedger(path).snapshot(
        "ai-work",
        now=20.1,
    )
    assert pressure.active == 0


def test_shared_pressure_configuration_is_all_or_none(tmp_path) -> None:
    pressure = SqliteSharedPressureLedger(tmp_path / "pressure.sqlite3")

    with pytest.raises(ValueError, match="configured together"):
        AdmissionRuntime(shared_pressure_ledger=pressure)

    with pytest.raises(ValueError, match="configured together"):
        AdmissionRuntime(
            shared_pressure_scope="ai-work",
            shared_pressure_owner_id="worker-a",
        )

def test_default_tenant_quota_is_provisioned_on_first_admission() -> None:
    ledger = TenantQuotaLedger()
    runtime = AdmissionRuntime(
        quota_ledger=ledger,
        default_tenant_quota=TenantQuota(
            window_id="default-window",
            max_operations=10,
            max_input_tokens=1_000,
            max_output_tokens=1_000,
            max_cost_usd=10.0,
            max_tool_calls=100,
            max_artifact_bytes=1024,
            max_storage_bytes=2048,
            max_concurrent_operations=4,
        ),
    )

    lease = runtime.admit(
        _request(
            "op-autoprovision",
            tenant_id="tenant-new",
            input_tokens=5,
            cost_usd=0.1,
        ),
        now_wall=10.0,
    )

    assert lease.quota_reservation is not None
    snapshot = ledger.snapshot("tenant-new")
    assert snapshot["window_id"] == "default-window"
    assert snapshot["quota"]["max_storage_bytes"] == 2048
    assert snapshot["active_reservations"] == 1


def test_default_tenant_quota_reuses_existing_policy_without_replacement() -> None:
    ledger = TenantQuotaLedger()
    ledger.configure(
        "tenant-a",
        TenantQuota(
            window_id="existing-window",
            max_operations=3,
            max_input_tokens=500,
            max_output_tokens=500,
            max_cost_usd=5.0,
            max_tool_calls=50,
            max_artifact_bytes=512,
            max_storage_bytes=768,
            max_concurrent_operations=2,
        ),
    )
    runtime = AdmissionRuntime(
        quota_ledger=ledger,
        default_tenant_quota=TenantQuota(
            window_id="default-window",
            max_operations=10,
            max_input_tokens=1_000,
            max_output_tokens=1_000,
            max_cost_usd=10.0,
            max_tool_calls=100,
            max_artifact_bytes=1024,
            max_storage_bytes=2048,
            max_concurrent_operations=4,
        ),
    )

    runtime.admit(
        _request(
            "op-existing-policy",
            tenant_id="tenant-a",
            input_tokens=5,
            cost_usd=0.1,
        ),
        now_wall=10.0,
    )

    snapshot = ledger.snapshot("tenant-a")
    assert snapshot["window_id"] == "existing-window"
    assert snapshot["quota"]["max_storage_bytes"] == 768

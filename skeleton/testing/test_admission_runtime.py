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
    TenantQuota,
    TenantQuotaLedger,
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
        "quota_enabled": False,
    }

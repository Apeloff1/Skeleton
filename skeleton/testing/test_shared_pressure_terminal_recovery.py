from __future__ import annotations

import hashlib

import pytest

from skeleton.ai.runtime.observability.cost_governor import (
    CostGovernor,
)
from skeleton.contracts.canonical import EvidenceRef
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
        window_id="shared-terminal-recovery",
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


def _evidence(label: str) -> tuple[EvidenceRef, ...]:
    return (
        EvidenceRef(
            source=f"test:shared-pressure-recovery:{label}",
            digest=hashlib.sha256(label.encode("utf-8")).hexdigest(),
            category="shared_pressure_recovery",
        ),
    )


def _configure(path) -> SqliteSharedPressureLedger:
    ledger = SqliteSharedPressureLedger(path)
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


def _governor(path, pressure: SqliteSharedPressureLedger) -> CostGovernor:
    return CostGovernor.durable(
        path,
        default_tenant_quota=_quota(),
        shared_pressure_ledger=pressure,
        shared_pressure_scope="ai-runtime",
        shared_pressure_owner_id="worker-a",
    )


def _pressure_active(
    pressure: SqliteSharedPressureLedger,
    *,
    now: float,
) -> int:
    return pressure.snapshot(
        "ai-runtime",
        tenant_id="tenant-a",
        now=now,
    ).active


def test_completion_recovery_releases_pressure_after_crash_between_ledgers(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "runtime.sqlite3"
    pressure = _configure(path)
    operation = "op-completion-pressure-crash"
    first = _governor(path, pressure)
    first.reserve(_request(operation), now_wall=10.0)

    def crash_before_pressure_release(_lease):
        raise SystemExit("simulated crash after quota completion")

    monkeypatch.setattr(
        first.runtime,
        "_release_shared_pressure",
        crash_before_pressure_release,
    )

    actual = UsageEstimate(
        input_tokens=80,
        output_tokens=15,
        cost_usd=0.4,
        wall_seconds=2.0,
        provider_attempts=1,
    )
    with pytest.raises(SystemExit):
        first.complete(
            operation,
            actual,
            evidence_refs=_evidence("completion"),
            now_wall=20.0,
        )

    quota_snapshot = first.runtime.quota_ledger.snapshot("tenant-a")
    assert quota_snapshot["completions"] == 1
    assert quota_snapshot["active_reservations"] == 0
    assert _pressure_active(pressure, now=20.0) == 1

    restarted_pressure = SqliteSharedPressureLedger(path)
    restarted = _governor(path, restarted_pressure)
    recovered = restarted.recover_completed(
        operation,
        evidence_refs=_evidence("completion"),
        now_wall=21.0,
    )

    assert recovered.state == "completed"
    assert recovered.accepted is True
    assert _pressure_active(restarted_pressure, now=21.0) == 0
    assert restarted.runtime.quota_ledger.snapshot("tenant-a")[
        "completions"
    ] == 1


def test_unspent_release_recovery_releases_pressure_after_quota_release(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "runtime.sqlite3"
    pressure = _configure(path)
    operation = "op-release-pressure-crash"
    first = _governor(path, pressure)
    first.reserve(_request(operation), now_wall=10.0)

    def crash_before_pressure_release(_lease):
        raise SystemExit("simulated crash after quota release")

    monkeypatch.setattr(
        first.runtime,
        "_release_shared_pressure",
        crash_before_pressure_release,
    )

    with pytest.raises(SystemExit):
        first.release_unspent(operation)

    quota_snapshot = first.runtime.quota_ledger.snapshot("tenant-a")
    assert quota_snapshot["active_reservations"] == 0
    assert quota_snapshot["completions"] == 0
    assert _pressure_active(pressure, now=20.0) == 1

    restarted_pressure = SqliteSharedPressureLedger(path)
    restarted = _governor(path, restarted_pressure)
    recovered = restarted.recover_released(
        operation,
        now_wall=21.0,
    )

    assert recovered.state == "released_unspent"
    assert recovered.accepted is False
    assert _pressure_active(restarted_pressure, now=21.0) == 0


def test_expired_pressure_is_already_settled_for_completion_recovery(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "runtime.sqlite3"
    pressure = _configure(path)
    operation = "op-completion-pressure-expired"
    first = _governor(path, pressure)
    first.reserve(_request(operation), now_wall=10.0)

    def crash_before_pressure_release(_lease):
        raise SystemExit("simulated crash after quota completion")

    monkeypatch.setattr(
        first.runtime,
        "_release_shared_pressure",
        crash_before_pressure_release,
    )

    with pytest.raises(SystemExit):
        first.complete(
            operation,
            UsageEstimate(
                input_tokens=80,
                output_tokens=15,
                cost_usd=0.4,
                wall_seconds=2.0,
                provider_attempts=1,
            ),
            evidence_refs=_evidence("expired"),
            now_wall=20.0,
        )

    restarted_pressure = SqliteSharedPressureLedger(path)
    restarted = _governor(path, restarted_pressure)
    recovered = restarted.recover_completed(
        operation,
        evidence_refs=_evidence("expired"),
        now_wall=100.0,
    )

    assert recovered.state == "completed"
    assert _pressure_active(restarted_pressure, now=100.0) == 0

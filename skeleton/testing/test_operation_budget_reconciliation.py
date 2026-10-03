from __future__ import annotations

import hashlib

import pytest

from skeleton.ai.runtime.observability.cost_governor import (
    CostGovernor,
    CostGovernorConflict,
    CostGovernorError,
)
from skeleton.contracts.canonical import EvidenceRef
from skeleton.intelligence.admission import (
    AdmissionRequest,
    ResourceBudget,
    UsageEstimate,
)
from skeleton.intelligence.admission_runtime import AdmissionRuntime
from skeleton.intelligence.quota import TenantQuota, TenantQuotaLedger


def _budget() -> ResourceBudget:
    return ResourceBudget(
        max_input_tokens=100,
        max_output_tokens=50,
        max_cost_usd=1.0,
        max_wall_seconds=5.0,
        max_provider_attempts=1,
        max_tool_calls=2,
        max_artifact_bytes=100,
        max_storage_bytes=100,
        max_concurrency=4,
        max_queue_depth=100,
    )


def _request(operation_id: str) -> AdmissionRequest:
    return AdmissionRequest(
        operation_id=operation_id,
        tenant_id="tenant-a",
        capability="model-inference",
        budget=_budget(),
        estimate=UsageEstimate(
            input_tokens=20,
            output_tokens=10,
            cost_usd=0.2,
            wall_seconds=1.0,
            provider_attempts=1,
        ),
    )


def _quota() -> TenantQuota:
    return TenantQuota(
        window_id="operation-budget-reconciliation",
        max_operations=100,
        max_input_tokens=100_000,
        max_output_tokens=100_000,
        max_cost_usd=100.0,
        max_tool_calls=100,
        max_artifact_bytes=10_000_000,
        max_storage_bytes=10_000_000,
        max_concurrent_operations=8,
    )


def _evidence(label: str) -> tuple[EvidenceRef, ...]:
    return (
        EvidenceRef(
            source=f"test:operation-budget:{label}",
            digest=hashlib.sha256(label.encode("utf-8")).hexdigest(),
            category="operation_budget_reconciliation",
        ),
    )


def _governor(path) -> CostGovernor:
    return CostGovernor.durable(
        path,
        default_tenant_quota=_quota(),
    )


def test_admission_completion_reports_operation_budget_overruns() -> None:
    ledger = TenantQuotaLedger()
    ledger.configure("tenant-a", _quota())
    runtime = AdmissionRuntime(quota_ledger=ledger)
    runtime.admit(_request("op-direct-overrun"), now_wall=10.0)

    completion = runtime.complete(
        "op-direct-overrun",
        UsageEstimate(
            input_tokens=101,
            output_tokens=51,
            cost_usd=1.1,
            wall_seconds=5.1,
            provider_attempts=2,
            tool_calls=3,
            artifact_bytes=101,
            storage_bytes=101,
        ),
        now_wall=11.0,
    )

    assert completion.operation_overrun is True
    assert completion.operation_overrun_dimensions == (
        "input_tokens",
        "output_tokens",
        "cost_usd",
        "wall_seconds",
        "provider_attempts",
        "tool_calls",
        "artifact_bytes",
        "storage_bytes",
    )
    assert completion.effective_actual is not None
    assert completion.effective_actual.cost_usd == pytest.approx(1.1)


def test_durable_metered_usage_participates_in_effective_actual_and_overrun() -> None:
    ledger = TenantQuotaLedger()
    ledger.configure("tenant-a", _quota())
    runtime = AdmissionRuntime(quota_ledger=ledger)
    runtime.admit(_request("op-metered-overrun"), now_wall=10.0)

    runtime.record_usage_event(
        "op-metered-overrun",
        "provider-actual",
        "provider",
        UsageEstimate(
            input_tokens=120,
            output_tokens=40,
            cost_usd=1.4,
        ),
        now_wall=10.5,
    )

    completion = runtime.complete(
        "op-metered-overrun",
        UsageEstimate(
            input_tokens=80,
            output_tokens=40,
            cost_usd=0.8,
            wall_seconds=2.0,
            provider_attempts=1,
        ),
        now_wall=11.0,
    )

    assert completion.effective_actual is not None
    assert completion.effective_actual.input_tokens == 120
    assert completion.effective_actual.cost_usd == pytest.approx(1.4)
    assert completion.operation_overrun_dimensions == (
        "input_tokens",
        "cost_usd",
    )

    telemetry = runtime.telemetry_snapshot()["metrics"]
    assert telemetry["counters"]["admission.operation_overrun_total"] == 1
    assert telemetry["counters"][
        "admission.operation_overrun.input_tokens_total"
    ] == 1
    assert telemetry["counters"][
        "admission.operation_overrun.cost_usd_total"
    ] == 1
    assert telemetry["samples"]["admission.actual.input_tokens"] == (120.0,)
    assert telemetry["samples"]["admission.actual.cost_usd"] == (1.4,)


def test_cost_governor_rejects_operation_overrun_as_terminal_evidence(
    tmp_path,
) -> None:
    governor = _governor(tmp_path / "quota.sqlite3")
    governor.reserve(_request("op-governor-overrun"), now_wall=10.0)

    decision = governor.complete(
        "op-governor-overrun",
        UsageEstimate(
            input_tokens=90,
            output_tokens=40,
            cost_usd=1.2,
            wall_seconds=6.0,
            provider_attempts=2,
        ),
        evidence_refs=_evidence("direct-overrun"),
        now_wall=11.0,
    )

    assert decision.state == "completed"
    assert decision.accepted is False
    assert (
        "operation-budget-overrun:cost_usd,wall_seconds,provider_attempts"
        in decision.reasons
    )
    snapshot = governor.runtime.quota_ledger.snapshot("tenant-a")
    assert snapshot["completions"] == 1
    assert snapshot["committed"]["cost_usd"] == pytest.approx(1.2)


def test_cost_governor_detects_metered_cost_overrun_even_if_reported_lower(
    tmp_path,
) -> None:
    governor = _governor(tmp_path / "quota.sqlite3")
    governor.reserve(_request("op-governor-metered"), now_wall=10.0)
    governor.charge(
        "op-governor-metered",
        "provider-metered",
        "provider",
        UsageEstimate(
            input_tokens=80,
            output_tokens=40,
            cost_usd=1.5,
        ),
        now_wall=10.5,
    )

    decision = governor.complete(
        "op-governor-metered",
        UsageEstimate(
            input_tokens=80,
            output_tokens=40,
            cost_usd=0.5,
            wall_seconds=2.0,
            provider_attempts=1,
        ),
        evidence_refs=_evidence("metered-overrun"),
        now_wall=11.0,
    )

    assert decision.accepted is False
    assert "operation-budget-overrun:cost_usd" in decision.reasons
    assert governor.runtime.quota_ledger.snapshot("tenant-a")[
        "committed"
    ]["cost_usd"] == pytest.approx(1.5)


def test_recovery_before_quota_completion_uses_journaled_completion_intent(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "quota.sqlite3"
    operation = "op-crash-before-quota-complete"
    first = _governor(path)
    first.reserve(_request(operation), now_wall=10.0)

    actual = UsageEstimate(
        input_tokens=90,
        output_tokens=40,
        cost_usd=1.25,
        wall_seconds=6.0,
        provider_attempts=2,
    )

    def crash_before_complete(*_args, **_kwargs):
        raise SystemExit("simulated process loss before quota completion")

    monkeypatch.setattr(first.runtime, "complete", crash_before_complete)

    with pytest.raises(SystemExit):
        first.complete(
            operation,
            actual,
            evidence_refs=_evidence("crash-before"),
            now_wall=11.0,
        )

    snapshot = first.runtime.quota_ledger.snapshot("tenant-a")
    assert snapshot["active_reservations"] == 1
    assert snapshot["completions"] == 0

    restarted = _governor(path)
    recovered = restarted.recover_completed(
        operation,
        evidence_refs=_evidence("crash-before"),
    )

    assert recovered.state == "completed"
    assert recovered.accepted is False
    assert (
        "operation-budget-overrun:cost_usd,wall_seconds,provider_attempts"
        in recovered.reasons
    )
    snapshot = restarted.runtime.quota_ledger.snapshot("tenant-a")
    assert snapshot["active_reservations"] == 0
    assert snapshot["completions"] == 1
    assert snapshot["committed"]["cost_usd"] == pytest.approx(1.25)


def test_recovery_after_quota_completion_preserves_same_overrun_decision(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "quota.sqlite3"
    operation = "op-crash-after-quota-complete"
    first = _governor(path)
    first.reserve(_request(operation), now_wall=10.0)

    actual = UsageEstimate(
        input_tokens=90,
        output_tokens=40,
        cost_usd=1.3,
        wall_seconds=6.5,
        provider_attempts=2,
    )

    original = first._completed_decision

    def crash_after_completion(**_kwargs):
        raise SystemExit("simulated process loss before qualification")

    monkeypatch.setattr(first, "_completed_decision", crash_after_completion)

    with pytest.raises(SystemExit):
        first.complete(
            operation,
            actual,
            evidence_refs=_evidence("crash-after"),
            now_wall=11.0,
        )

    # Quota completion committed before the qualification crash.
    snapshot = first.runtime.quota_ledger.snapshot("tenant-a")
    assert snapshot["active_reservations"] == 0
    assert snapshot["completions"] == 1

    # Restore is only for clarity inside this process; recovery uses a new one.
    monkeypatch.setattr(first, "_completed_decision", original)

    restarted = _governor(path)
    recovered = restarted.recover_completed(
        operation,
        evidence_refs=_evidence("crash-after"),
    )

    assert recovered.accepted is False
    assert (
        "operation-budget-overrun:cost_usd,wall_seconds,provider_attempts"
        in recovered.reasons
    )


def test_completion_intent_blocks_unspent_release_after_restart(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "quota.sqlite3"
    operation = "op-intent-not-unspent"
    request = _request(operation)
    first = _governor(path)
    first.reserve(request, now_wall=10.0)

    def crash_before_complete(*_args, **_kwargs):
        raise SystemExit("simulated completion handoff crash")

    monkeypatch.setattr(first.runtime, "complete", crash_before_complete)
    with pytest.raises(SystemExit):
        first.complete(
            operation,
            UsageEstimate(
                input_tokens=50,
                output_tokens=20,
                cost_usd=0.7,
                wall_seconds=2.0,
                provider_attempts=1,
            ),
            evidence_refs=_evidence("intent"),
            now_wall=11.0,
        )

    restarted = _governor(path)
    restarted.reserve(request, now_wall=20.0)

    with pytest.raises(
        CostGovernorConflict,
        match="completion intent cannot be released as unspent",
    ):
        restarted.release_unspent(operation)

    assert restarted.runtime.quota_ledger.snapshot("tenant-a")[
        "active_reservations"
    ] == 1


def test_failed_runtime_completion_clears_intent_for_safe_retry(
    tmp_path,
) -> None:
    path = tmp_path / "quota.sqlite3"
    operation = "op-clear-intent"
    governor = _governor(path)
    governor.reserve(_request(operation), now_wall=10.0)
    governor.mark_usage_unknown(
        operation,
        "provider-unknown",
        "provider",
        "provider omitted usage",
        now_wall=10.5,
    )

    with pytest.raises(
        CostGovernorError,
        match="actual_usage_unknown:provider",
    ):
        governor.complete(
            operation,
            UsageEstimate(),
            evidence_refs=_evidence("first-attempt"),
            now_wall=11.0,
        )

    assert governor._journal is not None
    record = governor._journal.load(operation)
    assert record is not None
    assert record.completion_intent is None


def test_legacy_completed_recovery_without_intent_fails_closed(
    tmp_path,
) -> None:
    path = tmp_path / "quota.sqlite3"
    operation = "op-legacy-no-intent"
    first = _governor(path)
    first.reserve(_request(operation), now_wall=10.0)

    # Simulate the pre-intent implementation: durable quota completion exists,
    # but the cost journal has no terminal-actual intent.
    first.runtime.complete(
        operation,
        UsageEstimate(
            input_tokens=50,
            output_tokens=20,
            cost_usd=0.7,
            wall_seconds=2.0,
            provider_attempts=1,
        ),
        now_wall=11.0,
    )

    restarted = _governor(path)
    recovered = restarted.recover_completed(
        operation,
        evidence_refs=_evidence("legacy"),
    )

    assert recovered.state == "completed"
    assert recovered.accepted is False
    assert (
        "operation-budget-recovery-intent-missing"
        in recovered.reasons
    )

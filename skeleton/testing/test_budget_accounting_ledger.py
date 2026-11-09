from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from skeleton.contracts.canonical import EvidenceRef
from skeleton.intelligence.admission import UsageEstimate
from skeleton.intelligence.quota import (
    QuotaConflict,
    TenantQuota,
)
from skeleton.observability.budget_accounting import (
    BudgetAccountingError,
    DurableBudgetAccountingLedger,
    qualify_budget_accounting,
)


def _quota(**overrides: object) -> TenantQuota:
    values: dict[str, object] = {
        "window_id": "window-1",
        "max_operations": 10,
        "max_input_tokens": 10_000,
        "max_output_tokens": 10_000,
        "max_cost_usd": 100.0,
        "max_tool_calls": 100,
        "max_artifact_bytes": 10_000,
        "max_storage_bytes": 10_000,
        "max_concurrent_operations": 4,
    }
    values.update(overrides)
    return TenantQuota(**values)


def _evidence() -> tuple[EvidenceRef, ...]:
    return (
        EvidenceRef(
            source="ci://dist-05/accounting",
            digest="a" * 64,
            category="cost_reconciliation",
        ),
    )


def test_reservation_and_charge_retries_are_idempotent(
    tmp_path: Path,
) -> None:
    ledger = DurableBudgetAccountingLedger(tmp_path / "quota.sqlite3")
    ledger.configure("tenant-a", _quota())
    estimate = UsageEstimate(
        input_tokens=100,
        output_tokens=10,
        cost_usd=1.0,
    )

    first = ledger.reserve(
        "tenant-a",
        "op-1",
        estimate,
        now=10.0,
    )
    replay = ledger.reserve(
        "tenant-a",
        "op-1",
        estimate,
        now=99.0,
    )
    assert replay == first
    assert replay.reserved_at == 10.0

    charge = ledger.charge(
        first.reservation_id,
        "charge-1",
        "provider",
        UsageEstimate(
            input_tokens=80,
            output_tokens=8,
            cost_usd=0.75,
        ),
        now=10.5,
    )
    charge_replay = ledger.charge(
        first.reservation_id,
        "charge-1",
        "provider",
        UsageEstimate(
            input_tokens=80,
            output_tokens=8,
            cost_usd=0.75,
        ),
        now=999.0,
    )
    assert charge_replay == charge
    snapshot = ledger.snapshot("tenant-a")
    assert snapshot["usage_events"] == 1
    assert snapshot["reserved"]["cost_usd"] == pytest.approx(1.0)


def test_charge_id_cannot_be_reused_with_different_usage(
    tmp_path: Path,
) -> None:
    ledger = DurableBudgetAccountingLedger(tmp_path / "quota.sqlite3")
    ledger.configure("tenant-a", _quota())
    reservation = ledger.reserve(
        "tenant-a",
        "op-1",
        UsageEstimate(cost_usd=2.0),
    )
    ledger.charge(
        reservation.reservation_id,
        "charge-1",
        "provider",
        UsageEstimate(cost_usd=0.5),
    )

    with pytest.raises(
        QuotaConflict,
        match="replayed with different inputs",
    ):
        ledger.charge(
            reservation.reservation_id,
            "charge-1",
            "provider",
            UsageEstimate(cost_usd=0.6),
        )


def test_restart_preserves_charge_and_qualification(
    tmp_path: Path,
) -> None:
    path = tmp_path / "quota.sqlite3"
    first = DurableBudgetAccountingLedger(path)
    first.configure("tenant-a", _quota())
    reservation = first.reserve(
        "tenant-a",
        "op-restart",
        UsageEstimate(
            input_tokens=100,
            cost_usd=1.0,
        ),
        now=10.0,
    )
    first.charge(
        reservation.reservation_id,
        "charge-restart",
        "provider",
        UsageEstimate(
            input_tokens=90,
            cost_usd=0.8,
        ),
        now=10.5,
    )

    restarted = DurableBudgetAccountingLedger(path)
    reservation_replay = restarted.reserve(
        "tenant-a",
        "op-restart",
        UsageEstimate(
            input_tokens=100,
            cost_usd=1.0,
        ),
        now=99.0,
    )
    assert reservation_replay == reservation

    completion = restarted.reconcile(
        reservation.reservation_id,
        UsageEstimate(
            input_tokens=90,
            cost_usd=0.8,
        ),
        now=11.0,
    )
    completion_replay = restarted.reconcile(
        reservation.reservation_id,
        UsageEstimate(
            input_tokens=90,
            cost_usd=0.8,
        ),
        now=88.0,
    )
    assert completion_replay == completion

    decision = restarted.qualification(
        tenant_id="tenant-a",
        operation_id="op-restart",
        reservation=reservation,
        completion=completion,
        evidence_refs=_evidence(),
    )
    assert decision.accepted is True
    assert decision.reasons == ()
    assert decision.usage_event_count == 1
    evidence = decision.accepted_evidence_ref()
    assert evidence.category == "budget_accounting"
    assert evidence.digest == decision.decision_digest


def test_unknown_usage_blocks_reconciliation_until_resolved(
    tmp_path: Path,
) -> None:
    path = tmp_path / "quota.sqlite3"
    ledger = DurableBudgetAccountingLedger(path)
    ledger.configure("tenant-a", _quota())
    reservation = ledger.reserve(
        "tenant-a",
        "op-unknown",
        UsageEstimate(storage_bytes=100),
    )
    marker = ledger.mark_charge_unknown(
        reservation.reservation_id,
        "charge-storage",
        "storage",
    )
    assert marker.category == "unknown:storage"

    with pytest.raises(
        QuotaConflict,
        match="actual_usage_unknown:storage",
    ):
        ledger.reconcile(
            reservation.reservation_id,
            UsageEstimate(),
        )

    resolved = ledger.resolve_unknown_charge(
        reservation.reservation_id,
        "charge-storage",
        UsageEstimate(storage_bytes=80),
        max_storage_bytes=100,
    )
    assert resolved.category == "storage"
    completion = ledger.reconcile(
        reservation.reservation_id,
        UsageEstimate(),
    )
    decision = ledger.qualification(
        tenant_id="tenant-a",
        operation_id="op-unknown",
        reservation=reservation,
        completion=completion,
        evidence_refs=_evidence(),
    )
    assert decision.accepted is True
    assert ledger.snapshot("tenant-a")["unknown_usage_events"] == 0


def test_tenant_overrun_is_promotion_blocking(
    tmp_path: Path,
) -> None:
    ledger = DurableBudgetAccountingLedger(tmp_path / "quota.sqlite3")
    ledger.configure(
        "tenant-a",
        _quota(max_cost_usd=1.0),
    )
    reservation = ledger.reserve(
        "tenant-a",
        "op-overrun",
        UsageEstimate(cost_usd=0.5),
    )
    ledger.charge(
        reservation.reservation_id,
        "charge-1",
        "provider",
        UsageEstimate(cost_usd=0.5),
    )
    completion = ledger.reconcile(
        reservation.reservation_id,
        UsageEstimate(cost_usd=2.0),
    )

    decision = ledger.qualification(
        tenant_id="tenant-a",
        operation_id="op-overrun",
        reservation=reservation,
        completion=completion,
        evidence_refs=_evidence(),
    )
    assert decision.accepted is False
    assert any(
        reason.startswith("completion-overrun:cost_usd")
        for reason in decision.reasons
    )
    assert any(
        reason.startswith("snapshot-over-quota:cost_usd")
        for reason in decision.reasons
    )
    with pytest.raises(
        BudgetAccountingError,
        match="cannot become promotion evidence",
    ):
        decision.accepted_evidence_ref()


def test_qualification_rejects_identity_and_snapshot_drift(
    tmp_path: Path,
) -> None:
    ledger = DurableBudgetAccountingLedger(tmp_path / "quota.sqlite3")
    ledger.configure("tenant-a", _quota())
    reservation = ledger.reserve(
        "tenant-a",
        "op-1",
        UsageEstimate(cost_usd=1.0),
    )
    ledger.charge(
        reservation.reservation_id,
        "charge-1",
        "provider",
        UsageEstimate(cost_usd=0.8),
    )
    completion = ledger.reconcile(
        reservation.reservation_id,
        UsageEstimate(cost_usd=0.8),
    )
    snapshot = ledger.snapshot("tenant-a")

    drift = dict(snapshot)
    drift["tenant_id"] = "tenant-b"
    drift["unknown_usage_events"] = 1
    drift["committed"] = {
        **snapshot["committed"],
        "cost_usd": 0.1,
    }
    decision = qualify_budget_accounting(
        tenant_id="tenant-a",
        operation_id="op-1",
        reservation=reservation,
        completion=completion,
        snapshot=drift,
        evidence_refs=_evidence(),
    )
    assert decision.accepted is False
    assert "snapshot-tenant-mismatch" in decision.reasons
    assert "unresolved-usage-events" in decision.reasons
    assert "committed-usage-underflow:cost_usd" in decision.reasons


def test_completion_substitution_is_rejected(
    tmp_path: Path,
) -> None:
    ledger = DurableBudgetAccountingLedger(tmp_path / "quota.sqlite3")
    ledger.configure("tenant-a", _quota())
    reservation = ledger.reserve(
        "tenant-a",
        "op-1",
        UsageEstimate(cost_usd=1.0),
    )
    ledger.charge(
        reservation.reservation_id,
        "charge-1",
        "provider",
        UsageEstimate(cost_usd=0.8),
    )
    completion = ledger.reconcile(
        reservation.reservation_id,
        UsageEstimate(cost_usd=0.8),
    )
    substituted = replace(
        completion,
        operation_id="other-op",
    )

    decision = qualify_budget_accounting(
        tenant_id="tenant-a",
        operation_id="op-1",
        reservation=reservation,
        completion=substituted,
        snapshot=ledger.snapshot("tenant-a"),
        evidence_refs=_evidence(),
    )
    assert decision.accepted is False
    assert "completion-operation-mismatch" in decision.reasons


def test_evidence_is_required(tmp_path: Path) -> None:
    ledger = DurableBudgetAccountingLedger(tmp_path / "quota.sqlite3")
    ledger.configure("tenant-a", _quota())
    reservation = ledger.reserve(
        "tenant-a",
        "op-1",
        UsageEstimate(cost_usd=1.0),
    )
    ledger.charge(
        reservation.reservation_id,
        "charge-1",
        "provider",
        UsageEstimate(cost_usd=0.8),
    )
    completion = ledger.reconcile(
        reservation.reservation_id,
        UsageEstimate(cost_usd=0.8),
    )

    with pytest.raises(
        BudgetAccountingError,
        match="evidence_refs must be non-empty",
    ):
        qualify_budget_accounting(
            tenant_id="tenant-a",
            operation_id="op-1",
            reservation=reservation,
            completion=completion,
            snapshot=ledger.snapshot("tenant-a"),
            evidence_refs=(),
        )

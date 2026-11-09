from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib

import pytest

from skeleton.ai.runtime.autonomous_engineering.effects import (
    EffectLedger,
    EffectLedgerError,
    SagaDefinition,
    SagaStep,
)


NOW = datetime(2026, 10, 2, 4, 15, tzinfo=timezone.utc)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def test_reservation_is_idempotent_and_payload_fenced(tmp_path) -> None:
    ledger = EffectLedger(tmp_path / "effects.sqlite3")
    first = ledger.reserve(
        effect_id="effect-1",
        operation_id="op-1",
        effect_kind="repo.patch",
        resource_ref="skeleton/core.py",
        idempotency_key="idem-1",
        request_digest=_sha("request"),
        compensable=True,
        now=NOW,
    )
    second = ledger.reserve(
        effect_id="effect-1",
        operation_id="op-1",
        effect_kind="repo.patch",
        resource_ref="skeleton/core.py",
        idempotency_key="idem-1",
        request_digest=_sha("request"),
        compensable=True,
        now=NOW,
    )
    assert second == first
    with pytest.raises(EffectLedgerError, match="reused for different"):
        ledger.reserve(
            effect_id="effect-2",
            operation_id="op-1",
            effect_kind="repo.patch",
            resource_ref="skeleton/other.py",
            idempotency_key="idem-1",
            request_digest=_sha("different"),
            compensable=True,
            now=NOW,
        )


def test_applied_effect_survives_reopen_and_compensates(tmp_path) -> None:
    path = tmp_path / "effects.sqlite3"
    ledger = EffectLedger(path)
    ledger.reserve(
        effect_id="effect-1",
        operation_id="op-1",
        effect_kind="repo.patch",
        resource_ref="skeleton/core.py",
        idempotency_key="idem-1",
        request_digest=_sha("request"),
        compensable=True,
        now=NOW,
    )
    applied = ledger.mark_applied(
        "effect-1",
        receipt_digest=_sha("patch-receipt"),
        now=NOW + timedelta(seconds=1),
    )
    assert applied.status == "applied"

    reopened = EffectLedger(path)
    recovered = reopened.get("effect-1")
    assert recovered is not None
    assert recovered.applied_receipt_digest == _sha("patch-receipt")
    compensated = reopened.mark_compensated(
        "effect-1",
        compensation_digest=_sha("rollback-receipt"),
        now=NOW + timedelta(seconds=2),
    )
    assert compensated.status == "compensated"


def test_applied_receipt_cannot_be_rewritten(tmp_path) -> None:
    ledger = EffectLedger(tmp_path / "effects.sqlite3")
    ledger.reserve(
        effect_id="effect-1",
        operation_id="op-1",
        effect_kind="repo.patch",
        resource_ref="skeleton/core.py",
        idempotency_key="idem-1",
        request_digest=_sha("request"),
        compensable=True,
        now=NOW,
    )
    ledger.mark_applied(
        "effect-1",
        receipt_digest=_sha("receipt-a"),
        now=NOW,
    )
    with pytest.raises(EffectLedgerError, match="identity conflict"):
        ledger.mark_applied(
            "effect-1",
            receipt_digest=_sha("receipt-b"),
            now=NOW,
        )


def test_retry_budget_is_fail_closed(tmp_path) -> None:
    ledger = EffectLedger(tmp_path / "effects.sqlite3")
    ledger.reserve(
        effect_id="effect-1",
        operation_id="op-1",
        effect_kind="repo.patch",
        resource_ref="skeleton/core.py",
        idempotency_key="idem-1",
        request_digest=_sha("request"),
        compensable=True,
        now=NOW,
    )
    ledger.mark_failed("effect-1", error_code="io_error", now=NOW)
    retried = ledger.retry(
        "effect-1",
        max_attempts=2,
        now=NOW + timedelta(seconds=1),
    )
    assert retried.status == "reserved"
    assert retried.attempt_count == 2
    ledger.mark_failed(
        "effect-1",
        error_code="io_error",
        now=NOW + timedelta(seconds=2),
    )
    with pytest.raises(EffectLedgerError, match="retry budget exhausted"):
        ledger.retry(
            "effect-1",
            max_attempts=2,
            now=NOW + timedelta(seconds=3),
        )


def test_compensation_candidates_are_reverse_effect_order(tmp_path) -> None:
    ledger = EffectLedger(tmp_path / "effects.sqlite3")
    for index in range(3):
        ledger.reserve(
            effect_id=f"effect-{index}",
            operation_id="op-1",
            effect_kind="repo.patch",
            resource_ref=f"file-{index}",
            idempotency_key=f"idem-{index}",
            request_digest=_sha(f"request-{index}"),
            compensable=True,
            now=NOW,
        )
        ledger.mark_applied(
            f"effect-{index}",
            receipt_digest=_sha(f"receipt-{index}"),
            now=NOW,
        )
    assert [row.effect_id for row in ledger.compensation_candidates("op-1")] == [
        "effect-2",
        "effect-1",
        "effect-0",
    ]


def test_noncompensable_effect_cannot_claim_compensation(tmp_path) -> None:
    ledger = EffectLedger(tmp_path / "effects.sqlite3")
    ledger.reserve(
        effect_id="effect-1",
        operation_id="op-1",
        effect_kind="external.publish",
        resource_ref="release",
        idempotency_key="idem-1",
        request_digest=_sha("request"),
        compensable=False,
        now=NOW,
    )
    ledger.mark_applied("effect-1", receipt_digest=_sha("receipt"), now=NOW)
    with pytest.raises(EffectLedgerError, match="not compensable"):
        ledger.mark_compensated(
            "effect-1",
            compensation_digest=_sha("rollback"),
            now=NOW,
        )


def test_saga_dependency_and_compensation_order() -> None:
    saga = SagaDefinition(
        saga_id="engineering-change",
        steps=(
            SagaStep("edit"),
            SagaStep("test", ("edit",)),
            SagaStep("publish", ("test",)),
        ),
    )
    assert saga.topological_order() == ("edit", "test", "publish")
    assert saga.ready(()) == ("edit",)
    assert saga.ready(("edit",)) == ("test",)
    assert saga.compensation_order(("edit", "test", "publish")) == (
        "publish",
        "test",
        "edit",
    )


def test_saga_cycle_is_rejected() -> None:
    with pytest.raises(ValueError, match="cycle"):
        SagaDefinition(
            saga_id="cycle",
            steps=(
                SagaStep("a", ("b",)),
                SagaStep("b", ("a",)),
            ),
        )

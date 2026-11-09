import json

from core.execution_evidence import derive_ledger, derive_lifecycle, verify_evidence_digest


def _audit(seq: int, kind: str, operation_id: str) -> dict:
    return {
        "seq": seq,
        "kind": kind,
        "detail": json.dumps({"operation_id": operation_id}),
    }


def test_pending_bound_is_derived_without_mutable_status():
    op = "a" * 32
    evidence = derive_lifecycle(
        op,
        pending_operations=[{"operation_id": op, "executor_bound": True}],
        receipts=[],
        audit_entries=[_audit(1, "operation_admitted", op)],
    )
    assert evidence.state == "pending_bound"
    assert evidence.confidence == "high"
    assert evidence.pending is True
    assert evidence.admitted_audit_present is True
    assert evidence.anomalies == ()
    assert verify_evidence_digest(evidence) is True


def test_receipt_plus_pending_means_executed_unconfirmed():
    op = "b" * 32
    evidence = derive_lifecycle(
        op,
        pending_operations=[{"operation_id": op, "executor_bound": True}],
        receipts=[{"operation_id": op}],
        audit_entries=[_audit(1, "operation_admitted", op), _audit(2, "operation_executed", op)],
    )
    assert evidence.state == "executed_unconfirmed"
    assert evidence.receipt_present is True
    assert evidence.executed_audit_present is True
    assert evidence.executed_audit_count == 1
    assert evidence.anomalies == ()


def test_receipt_and_execution_audit_without_queue_is_confirmed():
    op = "c" * 32
    evidence = derive_lifecycle(
        op,
        pending_operations=[],
        receipts=[{"operation_id": op}],
        audit_entries=[_audit(1, "operation_admitted", op), _audit(3, "operation_executed", op)],
    )
    assert evidence.state == "confirmed"
    assert evidence.confidence == "high"
    assert verify_evidence_digest(evidence) is True


def test_executed_audit_without_receipt_is_evidence_gap():
    op = "d" * 32
    evidence = derive_lifecycle(
        op,
        pending_operations=[],
        receipts=[],
        audit_entries=[_audit(1, "operation_admitted", op), _audit(4, "operation_executed", op)],
    )
    assert evidence.state == "evidence_gap"
    assert evidence.confidence == "low"
    assert "executed_without_receipt" in evidence.anomalies


def test_receipt_without_execution_audit_is_explicitly_unattested():
    op = "f" * 32
    evidence = derive_lifecycle(
        op,
        pending_operations=[],
        receipts=[{"operation_id": op}],
        audit_entries=[_audit(1, "operation_admitted", op)],
    )
    assert evidence.state == "receipt_unattested"
    assert "receipt_without_execution_audit" in evidence.anomalies


def test_failure_and_defer_counts_are_preserved():
    op = "e" * 32
    evidence = derive_lifecycle(
        op,
        pending_operations=[{"operation_id": op, "executor_bound": True}],
        receipts=[],
        audit_entries=[
            _audit(5, "operation_execution_failed", op),
            _audit(6, "operation_execution_deferred", op),
        ],
    )
    assert evidence.failed_audit_count == 1
    assert evidence.deferred_audit_count == 1
    assert evidence.audit_sequences == (5, 6)


def test_duplicate_execution_audit_is_detected():
    op = "9" * 32
    evidence = derive_lifecycle(
        op,
        pending_operations=[],
        receipts=[{"operation_id": op}],
        audit_entries=[
            _audit(1, "operation_admitted", op),
            _audit(2, "operation_executed", op),
            _audit(3, "operation_executed", op),
        ],
    )
    assert evidence.executed_audit_count == 2
    assert "duplicate_execution_audit" in evidence.anomalies


def test_duplicate_audit_sequence_is_detected():
    op = "8" * 32
    evidence = derive_lifecycle(
        op,
        pending_operations=[],
        receipts=[],
        audit_entries=[_audit(5, "operation_execution_failed", op), _audit(5, "operation_execution_deferred", op)],
    )
    assert "duplicate_audit_sequence" in evidence.anomalies


def test_evidence_digest_is_stable_for_same_facts():
    op = "7" * 32
    kwargs = dict(
        pending_operations=[{"operation_id": op, "executor_bound": False}],
        receipts=[],
        audit_entries=[_audit(1, "operation_admitted", op)],
    )
    first = derive_lifecycle(op, **kwargs)
    second = derive_lifecycle(op, **kwargs)
    assert first.evidence_sha256 == second.evidence_sha256
    assert verify_evidence_digest(first)


def test_ledger_discovers_operations_from_all_evidence_sources():
    pending = "1" * 32
    receipt = "2" * 32
    audit_only = "3" * 32
    ledger = derive_ledger(
        pending_operations=[{"operation_id": pending, "executor_bound": False}],
        receipts=[{"operation_id": receipt}],
        audit_entries=[_audit(7, "operation_execution_failed", audit_only)],
    )
    ids = {item.operation_id for item in ledger}
    assert ids == {pending, receipt, audit_only}
    assert all(len(item.evidence_sha256) == 64 for item in ledger)

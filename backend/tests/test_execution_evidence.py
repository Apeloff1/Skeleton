import json

from core.execution_evidence import derive_ledger, derive_lifecycle


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


def test_receipt_plus_pending_means_executed_unconfirmed():
    op = "b" * 32
    evidence = derive_lifecycle(
        op,
        pending_operations=[{"operation_id": op, "executor_bound": True}],
        receipts=[{"operation_id": op}],
        audit_entries=[_audit(2, "operation_executed", op)],
    )
    assert evidence.state == "executed_unconfirmed"
    assert evidence.receipt_present is True
    assert evidence.executed_audit_present is True


def test_receipt_and_execution_audit_without_queue_is_confirmed():
    op = "c" * 32
    evidence = derive_lifecycle(
        op,
        pending_operations=[],
        receipts=[{"operation_id": op}],
        audit_entries=[_audit(3, "operation_executed", op)],
    )
    assert evidence.state == "confirmed"
    assert evidence.confidence == "high"


def test_executed_audit_without_receipt_is_evidence_gap():
    op = "d" * 32
    evidence = derive_lifecycle(
        op,
        pending_operations=[],
        receipts=[],
        audit_entries=[_audit(4, "operation_executed", op)],
    )
    assert evidence.state == "evidence_gap"
    assert evidence.confidence == "low"


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

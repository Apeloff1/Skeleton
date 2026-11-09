from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.jeeves.agent.execution_audit import (
    AuditEventKind,
    ExecutionAuditError,
    ExecutionAuditLedger,
    ExecutionReplayVerifier,
    InMemoryExecutionAuditStore,
    ReplayIssueKind,
)


def _append_successful_operation(ledger: ExecutionAuditLedger, operation_id: str = "guard-op-1") -> None:
    ledger.append(
        AuditEventKind.INTENT_BOUND,
        {
            "intent_id": "intent-1",
            "intent_fingerprint": "a" * 64,
            "call_id": "call-1",
            "tool_name": "read_data",
        },
        operation_id=operation_id,
    )
    ledger.append(
        AuditEventKind.DECISION_MADE,
        {
            "decision_id": "decision-1",
            "decision_fingerprint": "b" * 64,
            "disposition": "act",
        },
        operation_id=operation_id,
    )
    ledger.append(
        AuditEventKind.AUTHORIZATION_ISSUED,
        {
            "token_id": "token-1",
            "decision_id": "decision-1",
            "authorization_fingerprint": "c" * 64,
        },
        operation_id=operation_id,
    )
    ledger.append(
        AuditEventKind.AUTHORIZATION_CONSUMED,
        {
            "token_id": "token-1",
            "permit_id": "permit-1",
            "authorization_fingerprint": "d" * 64,
        },
        operation_id=operation_id,
    )
    ledger.append(
        AuditEventKind.TOOL_OBSERVED,
        {
            "call_id": "call-1",
            "observation_fingerprint": "e" * 64,
            "ok": True,
        },
        operation_id=operation_id,
    )
    ledger.append(
        AuditEventKind.EVIDENCE_INGESTED,
        {
            "evidence_ids": ["evidence-1"],
            "evidence_fingerprint": "f" * 64,
        },
        operation_id=operation_id,
    )
    ledger.append(
        AuditEventKind.TRANSITION_LEARNED,
        {
            "experience_id": "transition-1",
            "model_fingerprint": "1" * 64,
        },
        operation_id=operation_id,
    )
    ledger.append(
        AuditEventKind.EXECUTION_FINALIZED,
        {
            "outcome": "success",
            "verification_score": 0.95,
        },
        operation_id=operation_id,
    )


def test_hash_chain_and_protocol_replay_validate_successful_operation() -> None:
    clock_values = iter(float(value) for value in range(1, 20))
    ledger = ExecutionAuditLedger("run-audit-1", clock=lambda: next(clock_values))
    _append_successful_operation(ledger)

    report = ExecutionReplayVerifier().verify(
        ledger.entries(),
        expected_run_id="run-audit-1",
        require_finalized_operations=True,
    )

    assert report.valid is True
    assert report.entries_checked == 8
    assert report.head_hash == ledger.head_hash
    assert len(report.operations) == 1
    operation = report.operations[0]
    assert operation.finalized is True
    assert operation.intent_fingerprint == "a" * 64
    assert operation.decision_id == "decision-1"
    assert operation.token_id == "token-1"
    assert operation.permit_id == "permit-1"
    assert operation.call_id == "call-1"
    assert operation.evidence_ids == ("evidence-1",)
    assert operation.experience_id == "transition-1"


def test_payload_tamper_is_detected_even_when_sequence_is_unchanged() -> None:
    ledger = ExecutionAuditLedger("run-audit-2", clock=lambda: 10.0)
    _append_successful_operation(ledger)
    entries = list(ledger.entries())
    tampered_payload = dict(entries[4].payload)
    tampered_payload["ok"] = False
    entries[4] = replace(entries[4], payload=tampered_payload)

    report = ExecutionReplayVerifier().verify(entries)

    assert report.valid is False
    assert any(issue.kind is ReplayIssueKind.EVENT_HASH_MISMATCH for issue in report.issues)


def test_previous_hash_splice_is_detected() -> None:
    ledger = ExecutionAuditLedger("run-audit-3", clock=lambda: 10.0)
    _append_successful_operation(ledger)
    entries = list(ledger.entries())
    entries[3] = replace(entries[3], previous_hash="9" * 64)

    report = ExecutionReplayVerifier().verify(entries)

    kinds = {issue.kind for issue in report.issues}
    assert ReplayIssueKind.PREVIOUS_HASH_MISMATCH in kinds
    assert ReplayIssueKind.EVENT_HASH_MISMATCH in kinds


def test_protocol_stage_skip_is_detected_even_with_valid_hashes() -> None:
    ledger = ExecutionAuditLedger("run-audit-4", clock=lambda: 10.0)
    ledger.append(
        AuditEventKind.INTENT_BOUND,
        {
            "intent_id": "intent-1",
            "intent_fingerprint": "a" * 64,
            "call_id": "call-1",
            "tool_name": "read_data",
        },
        operation_id="guard-op-skip",
    )
    ledger.append(
        AuditEventKind.AUTHORIZATION_ISSUED,
        {
            "token_id": "token-1",
            "authorization_fingerprint": "c" * 64,
        },
        operation_id="guard-op-skip",
    )

    report = ExecutionReplayVerifier().verify(ledger.entries())

    assert report.valid is False
    assert any(issue.kind is ReplayIssueKind.PROTOCOL_ORDER for issue in report.issues)


def test_call_identifier_substitution_is_detected_during_replay() -> None:
    ledger = ExecutionAuditLedger("run-audit-5", clock=lambda: 10.0)
    operation_id = "guard-op-id-mismatch"
    ledger.append(
        AuditEventKind.INTENT_BOUND,
        {
            "intent_id": "intent-1",
            "intent_fingerprint": "a" * 64,
            "call_id": "call-original",
            "tool_name": "read_data",
        },
        operation_id=operation_id,
    )
    ledger.append(
        AuditEventKind.DECISION_MADE,
        {
            "decision_id": "decision-1",
            "decision_fingerprint": "b" * 64,
            "disposition": "act",
        },
        operation_id=operation_id,
    )
    ledger.append(
        AuditEventKind.AUTHORIZATION_ISSUED,
        {
            "token_id": "token-1",
            "decision_id": "decision-1",
            "authorization_fingerprint": "c" * 64,
        },
        operation_id=operation_id,
    )
    ledger.append(
        AuditEventKind.AUTHORIZATION_CONSUMED,
        {
            "token_id": "token-1",
            "permit_id": "permit-1",
            "authorization_fingerprint": "d" * 64,
        },
        operation_id=operation_id,
    )
    ledger.append(
        AuditEventKind.TOOL_OBSERVED,
        {
            "call_id": "call-substituted",
            "observation_fingerprint": "e" * 64,
            "ok": True,
        },
        operation_id=operation_id,
    )

    report = ExecutionReplayVerifier().verify(ledger.entries())

    assert report.valid is False
    mismatch = [issue for issue in report.issues if issue.kind is ReplayIssueKind.IDENTIFIER_MISMATCH]
    assert mismatch
    assert mismatch[0].expected == "call-original"
    assert mismatch[0].actual == "call-substituted"


def test_operation_cannot_reopen_after_terminal_denial() -> None:
    ledger = ExecutionAuditLedger("run-audit-6", clock=lambda: 10.0)
    operation_id = "guard-op-terminal"
    ledger.append(
        AuditEventKind.INTENT_BOUND,
        {
            "intent_id": "intent-1",
            "intent_fingerprint": "a" * 64,
            "call_id": "call-1",
            "tool_name": "read_data",
        },
        operation_id=operation_id,
    )
    ledger.append(
        AuditEventKind.DECISION_MADE,
        {
            "decision_id": "decision-1",
            "decision_fingerprint": "b" * 64,
            "disposition": "abstain",
        },
        operation_id=operation_id,
    )
    ledger.append(
        AuditEventKind.EXECUTION_DENIED,
        {"reason": "uncertain"},
        operation_id=operation_id,
    )
    ledger.append(
        AuditEventKind.AUTHORIZATION_ISSUED,
        {
            "token_id": "token-1",
            "authorization_fingerprint": "c" * 64,
        },
        operation_id=operation_id,
    )

    report = ExecutionReplayVerifier().verify(ledger.entries())

    assert report.valid is False
    assert any(issue.kind is ReplayIssueKind.OPERATION_REOPENED for issue in report.issues)


def test_checkpoint_detects_head_or_count_mismatch() -> None:
    ledger = ExecutionAuditLedger("run-audit-7", clock=lambda: 10.0)
    _append_successful_operation(ledger)
    expected = ledger.checkpoint()
    ledger.append(
        AuditEventKind.CHECKPOINT_BOUND,
        {
            "checkpoint_sequence": 4,
            "checkpoint_fingerprint": "2" * 64,
        },
    )

    report = ExecutionReplayVerifier().verify(
        ledger.entries(),
        expected_checkpoint=expected,
    )

    assert report.valid is False
    assert any(issue.kind is ReplayIssueKind.CHECKPOINT_MISMATCH for issue in report.issues)


def test_restore_rejects_modified_export() -> None:
    ledger = ExecutionAuditLedger("run-audit-8", clock=lambda: 10.0)
    _append_successful_operation(ledger)
    exported = [dict(item) for item in ledger.export()]
    exported[2]["payload"] = {
        **dict(exported[2]["payload"]),
        "token_id": "token-forged",
    }

    with pytest.raises(ExecutionAuditError, match="invalid audit chain"):
        ExecutionAuditLedger.restore("run-audit-8", exported)


def test_store_preserves_chain_across_repeated_access() -> None:
    store = InMemoryExecutionAuditStore(clock=lambda: 42.0)
    first = store.get_or_create("run-audit-9")
    first.append(
        AuditEventKind.INTENT_BOUND,
        {
            "intent_id": "intent-1",
            "intent_fingerprint": "a" * 64,
            "call_id": "call-1",
            "tool_name": "read_data",
        },
        operation_id="guard-op-store",
    )
    second = store.get_or_create("run-audit-9")

    assert first is second
    assert second.event_count == 1
    report = store.verify("run-audit-9")
    assert report.valid is True
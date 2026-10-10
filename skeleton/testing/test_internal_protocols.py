from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from skeleton.contracts.protocol import (
    ProtocolEnvelope,
    RetryClass,
    UnknownOutcomePolicy,
)
from skeleton.distributed.network.internal_protocol import (
    ProtocolExecutionEnvelope,
    ProtocolExecutionError,
    ProtocolOutcome,
    ProtocolReceipt,
    canonical_payload_digest,
    validate_receipt,
)


ROOT = Path(__file__).resolve().parents[2]
A = "a" * 64
B = "b" * 64
C = "c" * 64


def _canonical(**overrides) -> ProtocolEnvelope:
    values = {
        "protocol": "internal.work",
        "message_id": "msg-001",
        "kind": "work.request",
        "sender": "planner",
        "recipient": "worker",
        "operation_id": "op-001",
        "correlation_id": "corr-001",
        "causation_id": "",
        "trace_id": "trace-001",
        "span_id": "span-001",
        "deadline_utc": "2026-10-07T20:00:00Z",
        "idempotency_key": "idem-op-001",
        "attempt": 1,
        "retry_class": RetryClass.NEVER,
        "unknown_outcome_policy": UnknownOutcomePolicy.FAIL_CLOSED,
        "payload": {"payload_digest": A},
    }
    values.update(overrides)
    return ProtocolEnvelope(**values)


def _execution(**overrides) -> ProtocolExecutionEnvelope:
    values = {
        "envelope": _canonical(),
        "tenant_id": "tenant-001",
        "authority_digest": B,
        "issued_at_utc": "2026-10-07T19:00:00Z",
        "max_attempts": 1,
        "attributes": (("priority", "high"),),
    }
    values.update(overrides)
    return ProtocolExecutionEnvelope(**values)


def test_network_layer_uses_canonical_protocol_envelope() -> None:
    execution = _execution()
    assert isinstance(execution.envelope, ProtocolEnvelope)
    assert execution.envelope.digest == execution.payload()["canonical_envelope_digest"]


def test_execution_digest_is_deterministic_across_attribute_order() -> None:
    left = _execution(attributes=(("z", "2"), ("a", "1")))
    right = _execution(attributes=(("a", "1"), ("z", "2")))
    assert left.attributes == (("a", "1"), ("z", "2"))
    assert left.execution_digest == right.execution_digest
    assert len(left.execution_digest) == 64


def test_duplicate_execution_attribute_is_rejected() -> None:
    with pytest.raises(ProtocolExecutionError, match="duplicate key"):
        _execution(attributes=(("priority", "high"), ("priority", "low")))


def test_non_retryable_execution_is_single_attempt() -> None:
    with pytest.raises(ProtocolExecutionError, match="one execution attempt"):
        _execution(max_attempts=2)


def test_retryable_execution_requires_deadline_and_attempt_budget() -> None:
    canonical = _canonical(
        retry_class=RetryClass.IDEMPOTENT,
        deadline_utc=None,
    )
    with pytest.raises(ProtocolExecutionError, match="requires canonical deadline"):
        _execution(envelope=canonical, max_attempts=2)

    canonical = _canonical(retry_class=RetryClass.IDEMPOTENT)
    with pytest.raises(ProtocolExecutionError, match="max_attempts >= 2"):
        _execution(envelope=canonical, max_attempts=1)


def test_retry_preserves_canonical_authority_and_deadline() -> None:
    first = _execution(
        envelope=_canonical(
            retry_class=RetryClass.IDEMPOTENT,
            unknown_outcome_policy=UnknownOutcomePolicy.IDEMPOTENT_REPLAY,
        ),
        max_attempts=3,
    )
    second = first.retry(
        message_id="msg-002",
        span_id="span-002",
        issued_at_utc="2026-10-07T19:05:00Z",
    )

    assert second.envelope.operation_id == first.envelope.operation_id
    assert second.envelope.correlation_id == first.envelope.correlation_id
    assert second.envelope.payload == first.envelope.payload
    assert second.tenant_id == first.tenant_id
    assert second.authority_digest == first.authority_digest
    assert second.envelope.deadline_utc == first.envelope.deadline_utc
    assert second.envelope.idempotency_key == first.envelope.idempotency_key
    assert second.envelope.attempt == 2
    assert second.envelope.causation_id == first.envelope.message_id
    assert second.previous_execution_digest == first.execution_digest


def test_retry_chain_is_digest_bound_and_bounded() -> None:
    first = _execution(
        envelope=_canonical(retry_class=RetryClass.IDEMPOTENT),
        max_attempts=3,
    )
    second = first.retry(
        message_id="msg-002",
        span_id="span-002",
        issued_at_utc="2026-10-07T19:05:00Z",
    )
    third = second.retry(
        message_id="msg-003",
        span_id="span-003",
        issued_at_utc="2026-10-07T19:10:00Z",
    )

    assert third.envelope.attempt == 3
    assert third.previous_execution_digest == second.execution_digest
    with pytest.raises(ProtocolExecutionError, match="budget exhausted"):
        third.retry(
            message_id="msg-004",
            span_id="span-004",
            issued_at_utc="2026-10-07T19:15:00Z",
        )


def test_retry_cannot_cross_canonical_deadline() -> None:
    execution = _execution(
        envelope=_canonical(retry_class=RetryClass.IDEMPOTENT),
        max_attempts=2,
    )
    with pytest.raises(ProtocolExecutionError, match="expired"):
        execution.retry(
            message_id="msg-002",
            span_id="span-002",
            issued_at_utc="2026-10-07T20:00:00Z",
        )


def test_retry_attempt_requires_predecessor_and_causation() -> None:
    canonical = _canonical(
        retry_class=RetryClass.IDEMPOTENT,
        message_id="msg-002",
        attempt=2,
        causation_id="msg-001",
    )
    with pytest.raises(ProtocolExecutionError, match="previous_execution_digest"):
        _execution(
            envelope=canonical,
            max_attempts=3,
            issued_at_utc="2026-10-07T19:05:00Z",
        )

    canonical = replace(canonical, causation_id="")
    with pytest.raises(ProtocolExecutionError, match="causation_id"):
        _execution(
            envelope=canonical,
            max_attempts=3,
            issued_at_utc="2026-10-07T19:05:00Z",
            previous_execution_digest=C,
        )


def test_child_preserves_operation_correlation_trace_tenant_and_authority() -> None:
    parent = _execution()
    child = parent.spawn_child(
        message_id="msg-child-001",
        span_id="span-child",
        recipient="storage",
        kind="state.commit",
        payload={"state_digest": C},
        issued_at_utc="2026-10-07T19:10:00Z",
    )

    assert child.envelope.operation_id == parent.envelope.operation_id
    assert child.envelope.correlation_id == parent.envelope.correlation_id
    assert child.envelope.trace_id == parent.envelope.trace_id
    assert child.envelope.causation_id == parent.envelope.message_id
    assert child.envelope.deadline_utc == parent.envelope.deadline_utc
    assert child.tenant_id == parent.tenant_id
    assert child.authority_digest == parent.authority_digest


def test_child_cannot_spawn_after_parent_deadline() -> None:
    with pytest.raises(ProtocolExecutionError, match="parent deadline"):
        _execution().spawn_child(
            message_id="msg-child-001",
            span_id="span-child",
            recipient="storage",
            kind="state.commit",
            payload={},
            issued_at_utc="2026-10-07T20:00:00Z",
        )


def test_trace_record_never_contains_raw_payload() -> None:
    execution = _execution()
    record = execution.trace_record(
        phase="dispatch",
        outcome=ProtocolOutcome.ACCEPTED,
    )

    assert record["canonical_envelope_digest"] == execution.envelope.digest
    assert record["execution_digest"] == execution.execution_digest
    assert record["trace_id"] == execution.envelope.trace_id
    assert record["outcome"] == "accepted"
    assert "payload" not in record


def test_unknown_outcome_policy_remains_canonical_contract_state() -> None:
    execution = _execution(
        envelope=_canonical(
            unknown_outcome_policy=UnknownOutcomePolicy.RECONCILE,
        )
    )
    assert execution.envelope.unknown_outcome_policy is UnknownOutcomePolicy.RECONCILE
    assert execution.payload()["unknown_outcome_policy"] == "reconcile"


def test_receipt_binds_canonical_and_execution_digests() -> None:
    execution = _execution()
    receipt = ProtocolReceipt.from_execution(
        execution,
        observer="worker",
        outcome=ProtocolOutcome.SUCCEEDED,
        observed_at_utc="2026-10-07T19:15:00Z",
        result_digest=C,
    )

    validate_receipt(execution, receipt)
    assert receipt.canonical_envelope_digest == execution.envelope.digest
    assert receipt.execution_digest == execution.execution_digest
    assert len(receipt.receipt_digest) == 64


def test_receipt_for_different_execution_fails_closed() -> None:
    left = _execution()
    right = _execution(
        envelope=_canonical(message_id="msg-other"),
    )
    receipt = ProtocolReceipt.from_execution(
        right,
        observer="worker",
        outcome=ProtocolOutcome.SUCCEEDED,
        observed_at_utc="2026-10-07T19:15:00Z",
    )
    with pytest.raises(ProtocolExecutionError, match="canonical envelope digest"):
        validate_receipt(left, receipt)


def test_receipt_cannot_predate_execution() -> None:
    with pytest.raises(ProtocolExecutionError, match="predate"):
        ProtocolReceipt.from_execution(
            _execution(),
            observer="worker",
            outcome=ProtocolOutcome.ACCEPTED,
            observed_at_utc="2026-10-07T18:59:59Z",
        )


def test_issued_time_must_precede_deadline() -> None:
    with pytest.raises(ProtocolExecutionError, match="precede canonical deadline"):
        _execution(issued_at_utc="2026-10-07T20:00:00Z")


def test_canonical_payload_digest_rejects_non_json_values() -> None:
    with pytest.raises(ProtocolExecutionError, match="canonical JSON"):
        canonical_payload_digest({"bad": {1, 2, 3}})


def test_execution_expiry_delegates_to_canonical_deadline() -> None:
    execution = _execution()
    before = datetime(2026, 10, 7, 19, 59, tzinfo=timezone.utc)
    at = datetime(2026, 10, 7, 20, 0, tzinfo=timezone.utc)
    assert execution.expired(now=before) is False
    assert execution.expired(now=at) is True


def test_canonical_and_ai_runtime_protocol_execution_files_are_identical() -> None:
    canonical = ROOT / "skeleton/distributed/network/internal_protocol.py"
    mirror = ROOT / "skeleton/ai/runtime/distributed/network/internal_protocol.py"
    assert canonical.read_bytes() == mirror.read_bytes()


def test_canonical_and_ai_runtime_network_exports_are_identical() -> None:
    canonical = ROOT / "skeleton/distributed/network/__init__.py"
    mirror = ROOT / "skeleton/ai/runtime/distributed/network/__init__.py"
    assert canonical.read_bytes() == mirror.read_bytes()

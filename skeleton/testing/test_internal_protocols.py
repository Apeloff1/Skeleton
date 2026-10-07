from __future__ import annotations

from dataclasses import replace
import math
from pathlib import Path

import pytest

from skeleton.distributed.network.internal_protocol import (
    DeliverySemantics,
    ProtocolEnvelope,
    ProtocolError,
    ProtocolOutcome,
    ProtocolReceipt,
    TraceContext,
    UnknownOutcomePolicy,
    canonical_payload_digest,
    validate_receipt,
)


ROOT = Path(__file__).resolve().parents[2]
A = "a" * 64
B = "b" * 64
C = "c" * 64


def _trace(*, span: str = "2" * 16) -> TraceContext:
    return TraceContext(
        trace_id="1" * 32,
        span_id=span,
        baggage=(("region", "test"), ("workload", "vol131")),
    )


def _envelope(**overrides) -> ProtocolEnvelope:
    values = {
        "message_id": "msg-001",
        "operation_id": "op-001",
        "correlation_id": "corr-001",
        "tenant_id": "tenant-001",
        "sender": "planner",
        "recipient": "worker",
        "message_type": "work.request",
        "payload_digest": A,
        "authority_digest": B,
        "trace": _trace(),
        "issued_at_ms": 1_000,
        "deadline_at_ms": 5_000,
        "delivery_semantics": DeliverySemantics.AT_MOST_ONCE,
        "unknown_outcome_policy": UnknownOutcomePolicy.FAIL_CLOSED,
        "attempt": 1,
        "max_attempts": 1,
        "attributes": (("priority", "high"),),
    }
    values.update(overrides)
    return ProtocolEnvelope(**values)


def test_protocol_digest_is_deterministic_across_attribute_order() -> None:
    left = _envelope(attributes=(("z", "2"), ("a", "1")))
    right = _envelope(attributes=(("a", "1"), ("z", "2")))

    assert left.attributes == (("a", "1"), ("z", "2"))
    assert left.envelope_digest == right.envelope_digest
    assert len(left.envelope_digest) == 64


def test_duplicate_protocol_attribute_is_rejected() -> None:
    with pytest.raises(ProtocolError, match="duplicate key"):
        _envelope(attributes=(("priority", "high"), ("priority", "low")))


def test_retry_preserves_operation_correlation_authority_and_deadline() -> None:
    parent = _envelope(
        delivery_semantics=DeliverySemantics.IDEMPOTENT_RETRY,
        unknown_outcome_policy=UnknownOutcomePolicy.QUERY_STATUS,
        idempotency_key="idem-op-001",
        max_attempts=3,
    )

    retry = parent.retry(
        message_id="msg-002",
        span_id="3" * 16,
        now_ms=1_250,
    )

    assert retry.operation_id == parent.operation_id
    assert retry.correlation_id == parent.correlation_id
    assert retry.tenant_id == parent.tenant_id
    assert retry.payload_digest == parent.payload_digest
    assert retry.authority_digest == parent.authority_digest
    assert retry.deadline_at_ms == parent.deadline_at_ms
    assert retry.idempotency_key == parent.idempotency_key
    assert retry.attempt == 2
    assert retry.max_attempts == 3
    assert retry.causation_id == parent.message_id
    assert retry.previous_envelope_digest == parent.envelope_digest
    assert retry.trace.trace_id == parent.trace.trace_id
    assert retry.trace.parent_span_id == parent.trace.span_id


def test_retry_chain_is_digest_bound_and_bounded() -> None:
    first = _envelope(
        delivery_semantics=DeliverySemantics.IDEMPOTENT_RETRY,
        idempotency_key="idem-op-001",
        max_attempts=3,
    )
    second = first.retry(
        message_id="msg-002",
        span_id="3" * 16,
        now_ms=1_100,
    )
    third = second.retry(
        message_id="msg-003",
        span_id="4" * 16,
        now_ms=1_200,
    )

    assert third.attempt == 3
    assert third.previous_envelope_digest == second.envelope_digest
    assert third.causation_id == second.message_id
    with pytest.raises(ProtocolError, match="budget exhausted"):
        third.retry(
            message_id="msg-004",
            span_id="5" * 16,
            now_ms=1_300,
        )


def test_retry_cannot_extend_or_cross_deadline() -> None:
    envelope = _envelope(
        delivery_semantics=DeliverySemantics.IDEMPOTENT_RETRY,
        idempotency_key="idem-op-001",
        max_attempts=2,
    )

    assert envelope.remaining_ms(4_999) == 1
    assert envelope.expired(5_000) is True
    with pytest.raises(ProtocolError, match="expired"):
        envelope.retry(
            message_id="msg-002",
            span_id="3" * 16,
            now_ms=5_000,
        )


def test_at_most_once_forbids_protocol_retry_budget() -> None:
    with pytest.raises(ProtocolError, match="at_most_once"):
        _envelope(max_attempts=2)

    envelope = _envelope()
    with pytest.raises(ProtocolError, match="not retryable"):
        envelope.retry(
            message_id="msg-002",
            span_id="3" * 16,
            now_ms=1_100,
        )


def test_retryable_delivery_requires_stable_idempotency_key() -> None:
    with pytest.raises(ProtocolError, match="idempotency_key"):
        _envelope(
            delivery_semantics=DeliverySemantics.IDEMPOTENT_RETRY,
            max_attempts=2,
        )


def test_non_root_retry_requires_predecessor_and_causation() -> None:
    with pytest.raises(ProtocolError, match="previous_envelope_digest"):
        _envelope(
            delivery_semantics=DeliverySemantics.IDEMPOTENT_RETRY,
            idempotency_key="idem-op-001",
            attempt=2,
            max_attempts=3,
            causation_id="msg-000",
        )

    with pytest.raises(ProtocolError, match="causation_id"):
        _envelope(
            delivery_semantics=DeliverySemantics.IDEMPOTENT_RETRY,
            idempotency_key="idem-op-001",
            attempt=2,
            max_attempts=3,
            previous_envelope_digest=C,
        )


def test_child_envelope_binds_causation_and_trace_parentage() -> None:
    parent = _envelope()
    child = parent.spawn_child(
        message_id="msg-child-001",
        span_id="3" * 16,
        recipient="storage",
        message_type="state.commit",
        payload_digest=C,
        now_ms=1_500,
    )

    assert child.operation_id == parent.operation_id
    assert child.correlation_id == parent.correlation_id
    assert child.tenant_id == parent.tenant_id
    assert child.sender == parent.recipient
    assert child.recipient == "storage"
    assert child.causation_id == parent.message_id
    assert child.deadline_at_ms == parent.deadline_at_ms
    assert child.trace.trace_id == parent.trace.trace_id
    assert child.trace.parent_span_id == parent.trace.span_id
    assert child.previous_envelope_digest is None


def test_child_cannot_spawn_after_parent_deadline() -> None:
    parent = _envelope()
    with pytest.raises(ProtocolError, match="parent deadline"):
        parent.spawn_child(
            message_id="msg-child-001",
            span_id="3" * 16,
            recipient="storage",
            message_type="state.commit",
            payload_digest=C,
            now_ms=parent.deadline_at_ms,
        )


def test_trace_record_contains_identity_and_digests_not_payload_content() -> None:
    envelope = _envelope()
    record = envelope.trace_record(
        phase="dispatch",
        outcome=ProtocolOutcome.ACCEPTED,
    )

    assert record["operation_id"] == envelope.operation_id
    assert record["correlation_id"] == envelope.correlation_id
    assert record["trace_id"] == envelope.trace.trace_id
    assert record["payload_digest"] == envelope.payload_digest
    assert record["envelope_digest"] == envelope.envelope_digest
    assert record["outcome"] == "accepted"
    assert "payload" not in record
    assert "baggage" not in record


def test_unknown_outcome_policy_is_explicit_and_stable() -> None:
    envelope = _envelope(
        unknown_outcome_policy=UnknownOutcomePolicy.RECONCILE,
    )

    assert envelope.unknown_outcome_action == "reconcile"
    assert envelope.payload()["unknown_outcome_policy"] == "reconcile"


def test_receipt_binds_exact_envelope_and_trace_identity() -> None:
    envelope = _envelope()
    receipt = ProtocolReceipt.from_envelope(
        envelope,
        observer="worker",
        outcome=ProtocolOutcome.SUCCEEDED,
        observed_at_ms=1_700,
        result_digest=C,
    )

    validate_receipt(envelope, receipt)
    assert receipt.envelope_digest == envelope.envelope_digest
    assert receipt.operation_id == envelope.operation_id
    assert receipt.correlation_id == envelope.correlation_id
    assert receipt.trace_id == envelope.trace.trace_id
    assert receipt.span_id == envelope.trace.span_id
    assert len(receipt.receipt_digest) == 64


def test_receipt_for_different_envelope_fails_closed() -> None:
    envelope = _envelope()
    other = _envelope(message_id="msg-other")
    receipt = ProtocolReceipt.from_envelope(
        other,
        observer="worker",
        outcome=ProtocolOutcome.SUCCEEDED,
        observed_at_ms=1_700,
    )

    with pytest.raises(ProtocolError, match="envelope digest"):
        validate_receipt(envelope, receipt)


def test_receipt_cannot_predate_envelope() -> None:
    envelope = _envelope()
    with pytest.raises(ProtocolError, match="predate"):
        ProtocolReceipt.from_envelope(
            envelope,
            observer="worker",
            outcome=ProtocolOutcome.ACCEPTED,
            observed_at_ms=999,
        )


def test_boolean_timestamps_are_rejected_as_integer_confusion() -> None:
    with pytest.raises(ProtocolError, match="issued_at_ms"):
        _envelope(issued_at_ms=True)


def test_trace_ids_and_self_parenting_fail_closed() -> None:
    with pytest.raises(ProtocolError, match="trace_id"):
        TraceContext(trace_id="not-a-trace", span_id="2" * 16)

    with pytest.raises(ProtocolError, match="parent itself"):
        TraceContext(
            trace_id="1" * 32,
            span_id="2" * 16,
            parent_span_id="2" * 16,
        )


def test_canonical_payload_digest_rejects_non_finite_numbers() -> None:
    with pytest.raises(ProtocolError, match="canonical JSON"):
        canonical_payload_digest({"score": math.nan})


def test_canonical_and_ai_runtime_protocol_files_are_byte_identical() -> None:
    canonical = ROOT / "skeleton/distributed/network/internal_protocol.py"
    mirror = ROOT / "skeleton/ai/runtime/distributed/network/internal_protocol.py"
    assert canonical.read_bytes() == mirror.read_bytes()


def test_canonical_and_ai_runtime_network_exports_are_byte_identical() -> None:
    canonical = ROOT / "skeleton/distributed/network/__init__.py"
    mirror = ROOT / "skeleton/ai/runtime/distributed/network/__init__.py"
    assert canonical.read_bytes() == mirror.read_bytes()

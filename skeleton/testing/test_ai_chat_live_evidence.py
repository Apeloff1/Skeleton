from __future__ import annotations

from datetime import UTC, datetime

import pytest

from skeleton.ai.assistant.attachments import (
    AttachmentAdmissionPlane,
    AttachmentUpload,
)
from skeleton.ai.assistant.contracts import SideEffectClass
from skeleton.ai.assistant.live_evidence import (
    LiveEvidenceBindingError,
    bind_governed_attachment,
    bind_provider_receipt_set,
    build_live_turn_evidence,
)
from skeleton.ai.assistant.turn_runtime import (
    TurnState,
    make_event,
    start_turn,
)


NOW = datetime(2026, 10, 7, 2, 50, tzinfo=UTC)
CONTEXT_DIGEST = "c" * 64


def _snapshot(operation_id: str = "operation-1"):
    snapshot = start_turn(
        operation_id=operation_id,
        request_digest="a" * 64,
        thread_id="thread-1",
        causal_user_message_id="user-1",
    )
    for state in (
        TurnState.ADMITTED,
        TurnState.USER_MESSAGE_COMMITTED,
        TurnState.CONTEXT_COMPILING,
        TurnState.ROUTING,
        TurnState.MODEL_RUNNING,
    ):
        snapshot = snapshot.apply(
            make_event(snapshot, state, observed_at=NOW)
        )
    return snapshot


def _attachment():
    payload = b"hello governed attachment"
    reference = AttachmentAdmissionPlane().admit(
        AttachmentUpload(
            payload=payload,
            declared_size=len(payload),
            claimed_mime="text/plain",
            filename="notes.txt",
            data_class="internal",
        )
    )
    return reference


def test_provider_receipt_set_is_order_invariant_and_content_minimized() -> None:
    first = bind_provider_receipt_set(
        operation_id="operation-1",
        execution_id="execution-1",
        context_digest=CONTEXT_DIGEST,
        provider_receipts=(
            "provider:local:receipt-b",
            "provider:local:receipt-a",
        ),
    )
    second = bind_provider_receipt_set(
        operation_id="operation-1",
        execution_id="execution-1",
        context_digest=CONTEXT_DIGEST,
        provider_receipts=(
            "provider:local:receipt-a",
            "provider:local:receipt-b",
        ),
    )
    assert first.digest == second.digest
    assert first.reference == "provider-set-sha256:" + first.digest
    assert first.receipt_count == 2
    encoded = str(first.as_dict())
    assert "provider:local:receipt-a" not in encoded
    assert "provider:local:receipt-b" not in encoded
    assert first.production_authority is False


def test_provider_receipt_set_requires_canonical_provider_refs() -> None:
    with pytest.raises(LiveEvidenceBindingError, match="provider:"):
        bind_provider_receipt_set(
            operation_id="operation-1",
            execution_id="execution-1",
            context_digest=CONTEXT_DIGEST,
            provider_receipts=("receipt-without-prefix",),
        )


def test_provider_receipt_set_rejects_duplicate_identity() -> None:
    with pytest.raises(LiveEvidenceBindingError, match="duplicate"):
        bind_provider_receipt_set(
            operation_id="operation-1",
            execution_id="execution-1",
            context_digest=CONTEXT_DIGEST,
            provider_receipts=(
                "provider:local:receipt-1",
                "provider:local:receipt-1",
            ),
        )


def test_provider_receipt_set_rejects_empty_execution_evidence() -> None:
    with pytest.raises(LiveEvidenceBindingError, match="must not be empty"):
        bind_provider_receipt_set(
            operation_id="operation-1",
            execution_id="execution-1",
            context_digest=CONTEXT_DIGEST,
            provider_receipts=(),
        )


def test_governed_attachment_replaces_payload_with_durable_refs() -> None:
    reference = _attachment()
    binding = bind_governed_attachment(
        reference,
        artifact_ref="artifact:tenant-a:object-1",
        governance_receipt_ref="governance:receipt-1",
        extraction_receipt_ref="extract:receipt-1",
    )
    assert binding.content_ref == reference.content_ref
    assert binding.source_digest == reference.source_digest
    assert binding.artifact_ref == "artifact:tenant-a:object-1"
    assert len(binding.governance_receipt_ref_hash) == 64
    assert len(binding.extraction_receipt_ref_hash or "") == 64
    assert binding.reference == "chat-attachment-binding-sha256:" + binding.digest
    encoded = str(binding.as_dict())
    assert "governance:receipt-1" not in encoded
    assert "extract:receipt-1" not in encoded
    assert "hello governed attachment" not in encoded
    assert binding.production_authority is False


def test_governed_attachment_requires_canonical_artifact_owner_ref() -> None:
    with pytest.raises(LiveEvidenceBindingError, match="artifact_ref"):
        bind_governed_attachment(
            _attachment(),
            artifact_ref="https://example.invalid/raw-file",
            governance_receipt_ref="governance:receipt-1",
        )


def test_quarantined_attachment_cannot_gain_governed_context_binding() -> None:
    payload = b"%PDF-1.7\n/OpenAction <<>>\n%%EOF"
    reference = AttachmentAdmissionPlane().admit(
        AttachmentUpload(
            payload=payload,
            declared_size=len(payload),
            claimed_mime="application/pdf",
            filename="active.pdf",
            data_class="internal",
        )
    )
    assert reference.quarantined is True
    with pytest.raises(LiveEvidenceBindingError, match="quarantined"):
        bind_governed_attachment(
            reference,
            artifact_ref="artifact:tenant-a:object-2",
            governance_receipt_ref="governance:receipt-2",
        )


def test_live_turn_evidence_binds_exact_snapshot_and_context() -> None:
    snapshot = _snapshot()
    provider = bind_provider_receipt_set(
        operation_id=snapshot.operation_id,
        execution_id="execution-1",
        context_digest=CONTEXT_DIGEST,
        provider_receipts=("provider:local:receipt-1",),
    )
    attachment = bind_governed_attachment(
        _attachment(),
        artifact_ref="artifact:tenant-a:object-1",
        governance_receipt_ref="governance:receipt-1",
    )
    envelope = build_live_turn_evidence(
        snapshot,
        context_digest=CONTEXT_DIGEST,
        provider=provider,
        tool_reconciliation_refs=("reconcile:tool-call-1",),
        attachments=(attachment,),
        claim_acceptance_digest="d" * 64,
    )
    assert envelope.operation_id == snapshot.operation_id
    assert envelope.provider_binding_digest == provider.digest
    assert envelope.attachment_binding_digests == (attachment.digest,)
    assert len(envelope.tool_reconciliation_ref_hashes) == 1
    assert envelope.claim_acceptance_digest == "d" * 64
    assert envelope.reference == "chat-live-evidence-sha256:" + envelope.digest
    assert envelope.production_authority is False


def test_live_turn_evidence_rejects_provider_from_another_operation() -> None:
    snapshot = _snapshot("operation-1")
    provider = bind_provider_receipt_set(
        operation_id="operation-2",
        execution_id="execution-1",
        context_digest=CONTEXT_DIGEST,
        provider_receipts=("provider:local:receipt-1",),
    )
    with pytest.raises(LiveEvidenceBindingError, match="another turn operation"):
        build_live_turn_evidence(
            snapshot,
            context_digest=CONTEXT_DIGEST,
            provider=provider,
        )


def test_live_turn_evidence_rejects_context_drift() -> None:
    snapshot = _snapshot()
    provider = bind_provider_receipt_set(
        operation_id=snapshot.operation_id,
        execution_id="execution-1",
        context_digest="e" * 64,
        provider_receipts=("provider:local:receipt-1",),
    )
    with pytest.raises(LiveEvidenceBindingError, match="context differs"):
        build_live_turn_evidence(
            snapshot,
            context_digest=CONTEXT_DIGEST,
            provider=provider,
        )


def test_live_turn_evidence_blocks_ambiguous_external_effect() -> None:
    snapshot = _snapshot()
    snapshot = snapshot.apply(
        make_event(
            snapshot,
            TurnState.TOOL_REQUIRED,
            observed_at=NOW,
        )
    )
    snapshot = snapshot.apply(
        make_event(
            snapshot,
            TurnState.TOOL_EXECUTING,
            observed_at=NOW,
            tool_call_id="tool-call-1",
            tool_side_effect=SideEffectClass.EXTERNAL_WRITE,
            external_effect_started=True,
        )
    )
    with pytest.raises(LiveEvidenceBindingError, match="must reconcile"):
        build_live_turn_evidence(
            snapshot,
            context_digest=CONTEXT_DIGEST,
        )


def test_live_turn_evidence_rejects_duplicate_reconciliation_refs() -> None:
    with pytest.raises(LiveEvidenceBindingError, match="duplicate"):
        build_live_turn_evidence(
            _snapshot(),
            context_digest=CONTEXT_DIGEST,
            tool_reconciliation_refs=(
                "reconcile:tool-call-1",
                "reconcile:tool-call-1",
            ),
        )


def test_live_turn_evidence_rejects_duplicate_attachment_bindings() -> None:
    attachment = bind_governed_attachment(
        _attachment(),
        artifact_ref="artifact:tenant-a:object-1",
        governance_receipt_ref="governance:receipt-1",
    )
    with pytest.raises(LiveEvidenceBindingError, match="duplicate governed"):
        build_live_turn_evidence(
            _snapshot(),
            context_digest=CONTEXT_DIGEST,
            attachments=(attachment, attachment),
        )

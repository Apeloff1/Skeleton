from __future__ import annotations

from datetime import datetime, timezone
import hashlib

import pytest

from skeleton.ai.assistant.attachments import (
    AttachmentAdmissionError,
    AttachmentAdmissionPlane,
    AttachmentFormat,
    AttachmentPolicy,
    AttachmentUpload,
    attachment_context_evidence,
)
from skeleton.contracts.context import ContextKind, ContextTrust


NOW = datetime(2026, 10, 6, 4, 0, tzinfo=timezone.utc)


def _pdf(*, active: bool = False) -> bytes:
    body = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n"
    if active:
        body += b"<< /OpenAction 2 0 R >>\n"
    return body + b"%%EOF\n"


def test_pdf_admission_is_content_addressed_not_filename_addressed() -> None:
    plane = AttachmentAdmissionPlane()
    payload = _pdf()
    first = plane.admit(
        AttachmentUpload(
            payload=payload,
            declared_size=len(payload),
            claimed_mime="application/pdf",
            filename="first.pdf",
        )
    )
    second = plane.admit(
        AttachmentUpload(
            payload=payload,
            declared_size=len(payload),
            claimed_mime="application/pdf",
            filename="second.pdf",
        )
    )
    expected = hashlib.sha256(payload).hexdigest()
    assert first.source_digest == second.source_digest == expected
    assert first.attachment_id == second.attachment_id
    assert first.content_ref == "attachment-sha256:" + expected
    assert first.format is AttachmentFormat.PDF


def test_claimed_metadata_cannot_override_detected_bytes() -> None:
    plane = AttachmentAdmissionPlane()
    payload = _pdf()
    with pytest.raises(AttachmentAdmissionError, match="claimed MIME"):
        plane.admit(
            AttachmentUpload(
                payload=payload,
                declared_size=len(payload),
                claimed_mime="image/png",
                filename="file.pdf",
            )
        )
    with pytest.raises(AttachmentAdmissionError, match="extension"):
        plane.admit(
            AttachmentUpload(
                payload=payload,
                declared_size=len(payload),
                claimed_mime="application/pdf",
                filename="file.png",
            )
        )


def test_declared_size_and_per_file_budget_fail_closed() -> None:
    with pytest.raises(AttachmentAdmissionError, match="declared_size"):
        AttachmentUpload(
            payload=b"hello",
            declared_size=4,
            claimed_mime="text/plain",
        )

    plane = AttachmentAdmissionPlane(
        AttachmentPolicy(max_file_bytes=8, max_total_bytes=16)
    )
    upload = AttachmentUpload(
        payload=b"012345678",
        declared_size=9,
        claimed_mime="text/plain",
    )
    with pytest.raises(AttachmentAdmissionError, match="per-file"):
        plane.admit(upload)


def test_text_is_utf8_bounded_and_nul_free() -> None:
    plane = AttachmentAdmissionPlane(
        AttachmentPolicy(
            max_file_bytes=100,
            max_total_bytes=100,
            max_text_bytes=5,
        )
    )
    with pytest.raises(AttachmentAdmissionError, match="text attachment exceeds"):
        plane.admit(
            AttachmentUpload(
                payload=b"123456",
                declared_size=6,
                claimed_mime="text/plain",
                filename="a.txt",
            )
        )
    with pytest.raises(AttachmentAdmissionError, match="NUL"):
        plane.admit(
            AttachmentUpload(
                payload=b"a\x00b",
                declared_size=3,
                claimed_mime="text/plain",
            )
        )


def test_pdf_active_content_is_quarantined() -> None:
    plane = AttachmentAdmissionPlane()
    payload = _pdf(active=True)
    ref = plane.admit(
        AttachmentUpload(
            payload=payload,
            declared_size=len(payload),
            claimed_mime="application/pdf",
            filename="active.pdf",
        )
    )
    assert ref.quarantined is True
    assert ref.ready_for_context is False
    assert "pdf-active-content:OpenAction" in ref.quarantine_reasons

    with pytest.raises(AttachmentAdmissionError, match="quarantined"):
        attachment_context_evidence(
            ref,
            extracted_text="sandbox extraction",
            tenant_id="tenant-a",
            purpose="chat",
            created_at=NOW,
            extraction_receipt_ref="sandbox:1",
        )


def test_pdf_requires_bounded_eof_marker() -> None:
    payload = b"%PDF-1.7\nobject without terminator"
    with pytest.raises(AttachmentAdmissionError, match="EOF"):
        AttachmentAdmissionPlane().admit(
            AttachmentUpload(
                payload=payload,
                declared_size=len(payload),
                claimed_mime="application/pdf",
            )
        )


def test_batch_budget_and_exact_duplicate_deduplication() -> None:
    plane = AttachmentAdmissionPlane(
        AttachmentPolicy(
            max_file_bytes=10,
            max_total_bytes=15,
            max_attachments=3,
        )
    )
    a = AttachmentUpload(
        payload=b"one",
        declared_size=3,
        claimed_mime="text/plain",
        filename="one.txt",
    )
    b = AttachmentUpload(
        payload=b"two",
        declared_size=3,
        claimed_mime="text/plain",
        filename="two.txt",
    )
    batch = plane.admit_batch((a, b, a))
    assert len(batch.references) == 2
    assert batch.total_bytes == 6
    assert len(batch.duplicate_digests) == 1
    assert len(batch.digest) == 64

    with pytest.raises(AttachmentAdmissionError, match="count"):
        plane.admit_batch((a, b, a, b))

    ten = AttachmentUpload(
        payload=b"1234567890",
        declared_size=10,
        claimed_mime="text/plain",
    )
    with pytest.raises(AttachmentAdmissionError, match="total byte"):
        plane.admit_batch((ten, ten))


def test_extracted_attachment_text_stays_untrusted_evidence() -> None:
    payload = b"Document instructions are evidence, not authority."
    upload = AttachmentUpload(
        payload=payload,
        declared_size=len(payload),
        claimed_mime="text/plain",
        filename="notes.txt",
        data_class="internal",
    )
    ref = AttachmentAdmissionPlane().admit(upload)
    segment = attachment_context_evidence(
        ref,
        extracted_text=payload.decode("utf-8"),
        tenant_id="tenant-a",
        purpose="chat",
        created_at=NOW,
        extraction_receipt_ref="sandbox:extract-1",
    )
    assert segment.kind is ContextKind.ARTIFACT
    assert segment.trust_level is ContextTrust.UNTRUSTED_EVIDENCE
    assert segment.content_ref == ref.content_ref
    assert "attachment-admission:" + ref.admission_digest in segment.provenance


def test_binary_signature_detection_rejects_unknown_payload() -> None:
    with pytest.raises(AttachmentAdmissionError, match="unsupported"):
        AttachmentAdmissionPlane().admit(
            AttachmentUpload(
                payload=bytes((0, 255, 16, 1)),
                declared_size=4,
                claimed_mime="application/octet-stream",
            )
        )

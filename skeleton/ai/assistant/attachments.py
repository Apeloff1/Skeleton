"""Governed chat-attachment admission and evidence projection.

Raw upload bytes terminate at this boundary. The chat/conversation layer should
persist and exchange only content-addressed attachment references after
admission succeeds.

This module deliberately does not parse document semantics. It verifies bounded
container identity from bytes, quarantines active-content indicators, emits a
content-addressed admission receipt, and can project already-extracted text only
as untrusted artifact evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import re
from typing import Iterable

from skeleton.artifacts.multimodal_ingestion import (
    IngestReceipt,
    MediaProbe,
    MultimodalIngestionCore,
)
from skeleton.context.sources.artifact import artifact_segment
from skeleton.contracts.context import ContextSegment, ContextTrust


class AttachmentAdmissionError(ValueError):
    """An attachment cannot safely enter chat context."""


class AttachmentFormat(str, Enum):
    PDF = "pdf"
    PNG = "png"
    JPEG = "jpeg"
    TEXT = "text"


_MIME_BY_FORMAT = {
    AttachmentFormat.PDF: frozenset({"application/pdf"}),
    AttachmentFormat.PNG: frozenset({"image/png"}),
    AttachmentFormat.JPEG: frozenset({"image/jpeg", "image/jpg"}),
    AttachmentFormat.TEXT: frozenset(
        {
            "text/plain",
            "text/markdown",
            "text/csv",
            "application/json",
        }
    ),
}
_EXTENSION_BY_FORMAT = {
    AttachmentFormat.PDF: frozenset({".pdf"}),
    AttachmentFormat.PNG: frozenset({".png"}),
    AttachmentFormat.JPEG: frozenset({".jpg", ".jpeg"}),
    AttachmentFormat.TEXT: frozenset(
        {".txt", ".md", ".markdown", ".csv", ".json"}
    ),
}
_PDF_ACTIVE_MARKERS = (
    b"/OpenAction",
    b"/AA",
    b"/Launch",
    b"/EmbeddedFile",
)
_SAFE_FILENAME = re.compile(r"^[^\x00-\x1f\x7f]{1,255}$")


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AttachmentAdmissionError(
            "attachment metadata is not deterministic JSON"
        ) from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _normalized_filename(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise AttachmentAdmissionError("filename must be text")
    name = value.strip()
    if name != value or not _SAFE_FILENAME.fullmatch(name):
        raise AttachmentAdmissionError(
            "filename is not safe normalized text"
        )
    if "/" in name or "\\" in name or name in {".", ".."}:
        raise AttachmentAdmissionError(
            "filename must not contain a path"
        )
    return name


def _extension(filename: str | None) -> str | None:
    if filename is None or "." not in filename:
        return None
    return "." + filename.rsplit(".", 1)[1].lower()


def _detect_format(payload: bytes) -> AttachmentFormat:
    if payload.startswith(b"%PDF-"):
        return AttachmentFormat.PDF
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return AttachmentFormat.PNG
    if payload.startswith(b"\xff\xd8\xff"):
        return AttachmentFormat.JPEG

    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AttachmentAdmissionError(
            "unsupported attachment byte signature"
        ) from exc
    if "\x00" in text:
        raise AttachmentAdmissionError(
            "text attachment contains NUL bytes"
        )
    return AttachmentFormat.TEXT


@dataclass(frozen=True, slots=True)
class AttachmentPolicy:
    policy_id: str = "chat-attachment-v1"
    allowed_formats: frozenset[AttachmentFormat] = frozenset(
        {
            AttachmentFormat.PDF,
            AttachmentFormat.PNG,
            AttachmentFormat.JPEG,
            AttachmentFormat.TEXT,
        }
    )
    max_file_bytes: int = 20 * 1024 * 1024
    max_total_bytes: int = 50 * 1024 * 1024
    max_attachments: int = 16
    max_text_bytes: int = 2 * 1024 * 1024
    allowed_data_classes: frozenset[str] = frozenset(
        {"public", "internal", "confidential", "restricted"}
    )
    quarantine_pdf_active_content: bool = True

    def __post_init__(self) -> None:
        if (
            not isinstance(self.policy_id, str)
            or not self.policy_id.strip()
        ):
            raise AttachmentAdmissionError(
                "policy_id must be non-empty"
            )
        object.__setattr__(
            self,
            "policy_id",
            self.policy_id.strip(),
        )
        formats = frozenset(
            value
            if isinstance(value, AttachmentFormat)
            else AttachmentFormat(str(value))
            for value in self.allowed_formats
        )
        if not formats:
            raise AttachmentAdmissionError(
                "allowed_formats must not be empty"
            )
        object.__setattr__(self, "allowed_formats", formats)
        for name in (
            "max_file_bytes",
            "max_total_bytes",
            "max_attachments",
            "max_text_bytes",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 1
            ):
                raise AttachmentAdmissionError(
                    f"{name} must be a positive integer"
                )
        if self.max_file_bytes > self.max_total_bytes:
            raise AttachmentAdmissionError(
                "max_file_bytes cannot exceed max_total_bytes"
            )
        classes = frozenset(
            str(value).strip().lower()
            for value in self.allowed_data_classes
        )
        if not classes or "" in classes:
            raise AttachmentAdmissionError(
                "allowed_data_classes must contain normalized values"
            )
        object.__setattr__(self, "allowed_data_classes", classes)
        if not isinstance(
            self.quarantine_pdf_active_content,
            bool,
        ):
            raise AttachmentAdmissionError(
                "quarantine_pdf_active_content must be boolean"
            )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "policy_id": self.policy_id,
                "allowed_formats": sorted(
                    value.value for value in self.allowed_formats
                ),
                "max_file_bytes": self.max_file_bytes,
                "max_total_bytes": self.max_total_bytes,
                "max_attachments": self.max_attachments,
                "max_text_bytes": self.max_text_bytes,
                "allowed_data_classes": sorted(
                    self.allowed_data_classes
                ),
                "quarantine_pdf_active_content":
                    self.quarantine_pdf_active_content,
            }
        )


@dataclass(frozen=True, slots=True)
class AttachmentUpload:
    payload: bytes
    declared_size: int
    claimed_mime: str
    filename: str | None = None
    data_class: str = "internal"
    source_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.payload, (bytes, bytearray)):
            raise AttachmentAdmissionError("payload must be bytes")
        payload = bytes(self.payload)
        object.__setattr__(self, "payload", payload)
        if (
            isinstance(self.declared_size, bool)
            or not isinstance(self.declared_size, int)
            or self.declared_size < 0
        ):
            raise AttachmentAdmissionError(
                "declared_size must be a non-negative integer"
            )
        if self.declared_size != len(payload):
            raise AttachmentAdmissionError(
                "declared_size does not match attachment bytes"
            )
        if (
            not isinstance(self.claimed_mime, str)
            or not self.claimed_mime.strip()
        ):
            raise AttachmentAdmissionError(
                "claimed_mime must be non-empty"
            )
        object.__setattr__(
            self,
            "claimed_mime",
            self.claimed_mime.strip().lower(),
        )
        object.__setattr__(
            self,
            "filename",
            _normalized_filename(self.filename),
        )
        data_class = str(self.data_class).strip().lower()
        if not data_class:
            raise AttachmentAdmissionError(
                "data_class must be non-empty"
            )
        object.__setattr__(self, "data_class", data_class)
        if self.source_id is not None:
            source_id = str(self.source_id).strip()
            if not source_id or len(source_id) > 1024:
                raise AttachmentAdmissionError(
                    "source_id is invalid"
                )
            object.__setattr__(self, "source_id", source_id)


@dataclass(frozen=True, slots=True)
class AttachmentReference:
    attachment_id: str
    source_digest: str
    content_ref: str
    format: AttachmentFormat
    media_type: str
    byte_size: int
    data_class: str
    policy_digest: str
    admission_digest: str
    quarantined: bool
    quarantine_reasons: tuple[str, ...] = ()
    original_filename: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "source_digest",
            "policy_digest",
            "admission_digest",
        ):
            value = getattr(self, name)
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(
                    ch not in "0123456789abcdef"
                    for ch in value
                )
            ):
                raise AttachmentAdmissionError(
                    f"{name} must be lowercase sha256"
                )
        if not isinstance(self.format, AttachmentFormat):
            object.__setattr__(
                self,
                "format",
                AttachmentFormat(str(self.format)),
            )
        if (
            not isinstance(self.byte_size, int)
            or self.byte_size < 0
        ):
            raise AttachmentAdmissionError(
                "byte_size is invalid"
            )
        reasons = tuple(
            dict.fromkeys(
                str(value).strip()
                for value in self.quarantine_reasons
            )
        )
        if any(not value for value in reasons):
            raise AttachmentAdmissionError(
                "quarantine reasons must be non-empty"
            )
        object.__setattr__(
            self,
            "quarantine_reasons",
            reasons,
        )
        if bool(reasons) != self.quarantined:
            raise AttachmentAdmissionError(
                "quarantine flag must match quarantine reasons"
            )

    @property
    def ready_for_context(self) -> bool:
        return not self.quarantined

    def as_dict(self) -> dict[str, object]:
        return {
            "attachment_id": self.attachment_id,
            "source_digest": self.source_digest,
            "content_ref": self.content_ref,
            "format": self.format.value,
            "media_type": self.media_type,
            "byte_size": self.byte_size,
            "data_class": self.data_class,
            "policy_digest": self.policy_digest,
            "admission_digest": self.admission_digest,
            "quarantined": self.quarantined,
            "quarantine_reasons": list(
                self.quarantine_reasons
            ),
            "original_filename": self.original_filename,
        }


@dataclass(frozen=True, slots=True)
class AttachmentBatchReceipt:
    references: tuple[AttachmentReference, ...]
    total_bytes: int
    duplicate_digests: tuple[str, ...]
    digest: str

    def __post_init__(self) -> None:
        if self.total_bytes != sum(
            item.byte_size for item in self.references
        ):
            raise AttachmentAdmissionError(
                "attachment batch byte accounting mismatch"
            )
        expected = _digest(
            {
                "references": [
                    item.as_dict()
                    for item in self.references
                ],
                "total_bytes": self.total_bytes,
                "duplicate_digests": list(
                    self.duplicate_digests
                ),
            }
        )
        if self.digest != expected:
            raise AttachmentAdmissionError(
                "attachment batch digest mismatch"
            )


class AttachmentAdmissionPlane:
    def __init__(
        self,
        policy: AttachmentPolicy | None = None,
    ) -> None:
        self.policy = policy or AttachmentPolicy()

    def admit(
        self,
        upload: AttachmentUpload,
    ) -> AttachmentReference:
        if not isinstance(upload, AttachmentUpload):
            raise TypeError("upload must be AttachmentUpload")
        if upload.declared_size > self.policy.max_file_bytes:
            raise AttachmentAdmissionError(
                "attachment exceeds per-file byte limit"
            )
        if (
            upload.data_class
            not in self.policy.allowed_data_classes
        ):
            raise AttachmentAdmissionError(
                "attachment data class is not admitted"
            )

        format_ = _detect_format(upload.payload)
        if format_ not in self.policy.allowed_formats:
            raise AttachmentAdmissionError(
                "attachment format is not admitted"
            )
        if upload.claimed_mime not in _MIME_BY_FORMAT[format_]:
            raise AttachmentAdmissionError(
                "claimed MIME does not match attachment bytes"
            )
        extension = _extension(upload.filename)
        if (
            extension is not None
            and extension not in _EXTENSION_BY_FORMAT[format_]
        ):
            raise AttachmentAdmissionError(
                "filename extension does not match attachment bytes"
            )
        if (
            format_ is AttachmentFormat.TEXT
            and len(upload.payload) > self.policy.max_text_bytes
        ):
            raise AttachmentAdmissionError(
                "text attachment exceeds configured byte limit"
            )
        if format_ is AttachmentFormat.PDF:
            if b"%%EOF" not in upload.payload[-2048:]:
                raise AttachmentAdmissionError(
                    "PDF is missing bounded EOF marker"
                )

        reasons: list[str] = []
        if (
            format_ is AttachmentFormat.PDF
            and self.policy.quarantine_pdf_active_content
        ):
            for marker in _PDF_ACTIVE_MARKERS:
                if marker in upload.payload:
                    reasons.append(
                        "pdf-active-content:"
                        + marker.decode(
                            "ascii",
                            errors="ignore",
                        ).lstrip("/")
                    )

        source_digest = _sha256(upload.payload)
        media_type = (
            "image"
            if format_
            in {
                AttachmentFormat.PNG,
                AttachmentFormat.JPEG,
            }
            else "document"
            if format_ is AttachmentFormat.PDF
            else "text"
        )
        attachment_id = "ATT." + source_digest[:32]
        admission_payload = {
            "attachment_id": attachment_id,
            "source_digest": source_digest,
            "format": format_.value,
            "media_type": media_type,
            "byte_size": len(upload.payload),
            "data_class": upload.data_class,
            "policy_digest": self.policy.digest,
            "quarantine_reasons": sorted(set(reasons)),
        }
        return AttachmentReference(
            attachment_id=attachment_id,
            source_digest=source_digest,
            content_ref="attachment-sha256:" + source_digest,
            format=format_,
            media_type=media_type,
            byte_size=len(upload.payload),
            data_class=upload.data_class,
            policy_digest=self.policy.digest,
            admission_digest=_digest(admission_payload),
            quarantined=bool(reasons),
            quarantine_reasons=tuple(
                sorted(set(reasons))
            ),
            original_filename=upload.filename,
        )

    def admit_batch(
        self,
        uploads: Iterable[AttachmentUpload],
    ) -> AttachmentBatchReceipt:
        values = tuple(uploads)
        if len(values) > self.policy.max_attachments:
            raise AttachmentAdmissionError(
                "attachment count exceeds configured limit"
            )
        if any(
            not isinstance(upload, AttachmentUpload)
            for upload in values
        ):
            raise TypeError(
                "uploads must contain only AttachmentUpload values"
            )
        declared_total = sum(
            upload.declared_size
            for upload in values
        )
        if declared_total > self.policy.max_total_bytes:
            raise AttachmentAdmissionError(
                "attachment batch exceeds total byte limit"
            )

        admitted: list[AttachmentReference] = []
        seen: set[str] = set()
        duplicates: list[str] = []
        for upload in values:
            reference = self.admit(upload)
            if reference.source_digest in seen:
                duplicates.append(
                    reference.source_digest
                )
                continue
            seen.add(reference.source_digest)
            admitted.append(reference)

        total = sum(
            item.byte_size for item in admitted
        )
        payload = {
            "references": [
                item.as_dict()
                for item in admitted
            ],
            "total_bytes": total,
            "duplicate_digests": sorted(duplicates),
        }
        return AttachmentBatchReceipt(
            references=tuple(admitted),
            total_bytes=total,
            duplicate_digests=tuple(
                sorted(duplicates)
            ),
            digest=_digest(payload),
        )


def admit_multimodal_reference(
    reference: AttachmentReference,
    *,
    payload: bytes,
    probe: MediaProbe,
    ingestion: MultimodalIngestionCore,
    trust_label: str = "untrusted",
) -> IngestReceipt:
    """Bind an admitted image reference into canonical multimodal ingestion."""

    if not isinstance(reference, AttachmentReference):
        raise TypeError("reference must be AttachmentReference")
    if not isinstance(probe, MediaProbe):
        raise TypeError("probe must be MediaProbe")
    if not isinstance(ingestion, MultimodalIngestionCore):
        raise TypeError("ingestion must be MultimodalIngestionCore")
    if not reference.ready_for_context:
        raise AttachmentAdmissionError(
            "quarantined attachment cannot enter multimodal ingestion"
        )
    if reference.media_type != "image":
        raise AttachmentAdmissionError(
            "attachment is not a supported multimodal image reference"
        )
    source = bytes(payload)
    if _sha256(source) != reference.source_digest:
        raise AttachmentAdmissionError(
            "multimodal payload does not match attachment digest"
        )
    if len(source) != reference.byte_size:
        raise AttachmentAdmissionError(
            "multimodal payload size does not match attachment reference"
        )
    if probe.media_type != reference.media_type:
        raise AttachmentAdmissionError(
            "multimodal probe media type differs from attachment reference"
        )
    if probe.format != reference.format.value:
        raise AttachmentAdmissionError(
            "multimodal probe format differs from attachment reference"
        )
    try:
        asset, receipt = ingestion.admit_predecode(
            source,
            probe,
            trust_label=trust_label,
            classification=reference.data_class,
            asset_id=reference.attachment_id,
        )
    except Exception as exc:
        raise AttachmentAdmissionError(
            "canonical multimodal ingestion rejected attachment"
        ) from exc
    if (
        asset.source_digest != reference.source_digest
        or receipt.source_digest != reference.source_digest
    ):
        raise AttachmentAdmissionError(
            "multimodal ingestion source digest drifted"
        )
    return receipt


def attachment_context_evidence(
    reference: AttachmentReference,
    *,
    extracted_text: str,
    tenant_id: str,
    purpose: str,
    created_at: datetime,
    extraction_receipt_ref: str,
) -> ContextSegment:
    """Project sandbox-extracted content as untrusted evidence only."""

    if not isinstance(reference, AttachmentReference):
        raise TypeError(
            "reference must be AttachmentReference"
        )
    if not reference.ready_for_context:
        raise AttachmentAdmissionError(
            "quarantined attachment cannot enter context"
        )
    if (
        not isinstance(extracted_text, str)
        or not extracted_text
    ):
        raise AttachmentAdmissionError(
            "extracted_text must be materialized"
        )
    if (
        not isinstance(extraction_receipt_ref, str)
        or not extraction_receipt_ref.strip()
    ):
        raise AttachmentAdmissionError(
            "extraction_receipt_ref must be non-empty"
        )
    if (
        created_at.tzinfo is None
        or created_at.utcoffset() is None
    ):
        raise AttachmentAdmissionError(
            "created_at must be timezone-aware"
        )

    segment = artifact_segment(
        artifact_id=reference.attachment_id,
        content=extracted_text,
        tenant_id=tenant_id,
        purpose=purpose,
        created_at=created_at.astimezone(timezone.utc),
        data_class=reference.data_class,
        content_ref=reference.content_ref,
        provenance=(
            "attachment-source-sha256:"
            + reference.source_digest,
            "attachment-admission:"
            + reference.admission_digest,
            "attachment-policy:"
            + reference.policy_digest,
            "attachment-extraction:"
            + extraction_receipt_ref.strip(),
        ),
        retention_class="chat-attachment",
    )
    if (
        segment.trust_level
        is not ContextTrust.UNTRUSTED_EVIDENCE
    ):
        raise AttachmentAdmissionError(
            "attachment evidence unexpectedly gained authority"
        )
    return segment


__all__ = [
    "AttachmentAdmissionError",
    "AttachmentAdmissionPlane",
    "AttachmentBatchReceipt",
    "AttachmentFormat",
    "AttachmentPolicy",
    "AttachmentReference",
    "AttachmentUpload",
    "admit_multimodal_reference",
    "attachment_context_evidence",
]

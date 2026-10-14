"""Content-minimized evidence bindings for live AI-chat integration.

The durable chat turn coordinates work but does not own provider transport,
artifact storage, tool execution, verification, or canonical conversation
state. This module stores bindings to those authorities instead of duplicating
payloads.

Every record is deterministic, digest-bound, and explicitly non-authoritative.
Raw provider receipts, attachment bytes, extracted document text, tool result
payloads, and model response prose are intentionally absent.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Iterable, Sequence

from .attachments import AttachmentReference
from .turn_runtime import TurnSnapshot, digest_json, operation_digest


LIVE_EVIDENCE_SCHEMA_VERSION = 1


class LiveEvidenceBindingError(ValueError):
    """Cross-plane evidence cannot be safely bound to one live chat turn."""


def _canonical_text(value: object, field: str, *, maximum: int = 2048) -> str:
    if not isinstance(value, str):
        raise LiveEvidenceBindingError(f"{field} must be text")
    normalized = value.strip()
    if (
        not normalized
        or normalized != value
        or len(normalized) > maximum
        or any(ord(ch) < 32 or ord(ch) == 127 for ch in normalized)
    ):
        raise LiveEvidenceBindingError(f"{field} is not canonical")
    return normalized


def _sha256(value: object, field: str) -> str:
    text = _canonical_text(value, field, maximum=64)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise LiveEvidenceBindingError(f"{field} must be lowercase sha256")
    return text


def _hash_ref(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalized_refs(
    values: Sequence[str] | Iterable[str],
    field: str,
    *,
    required_prefix: str | None = None,
    maximum_count: int = 256,
) -> tuple[str, ...]:
    raw = tuple(values)
    if len(raw) > maximum_count:
        raise LiveEvidenceBindingError(f"{field} exceeds maximum count")
    normalized: list[str] = []
    for item in raw:
        value = _canonical_text(item, field)
        if required_prefix is not None and not value.startswith(required_prefix):
            raise LiveEvidenceBindingError(
                f"{field} must use {required_prefix!r} references"
            )
        if value in normalized:
            raise LiveEvidenceBindingError(f"{field} contains duplicate identity")
        normalized.append(value)
    return tuple(sorted(normalized))


@dataclass(frozen=True, slots=True)
class ProviderReceiptSetBinding:
    """Hash-only binding for all provider receipts emitted by one execution."""

    operation_id: str
    execution_id: str
    context_digest: str
    receipt_ref_hashes: tuple[str, ...]
    receipt_count: int
    schema_version: int = LIVE_EVIDENCE_SCHEMA_VERSION
    authority_scope: str = "provider-receipt-set-binding-only"
    production_authority: bool = False

    def __post_init__(self) -> None:
        if self.schema_version != LIVE_EVIDENCE_SCHEMA_VERSION:
            raise LiveEvidenceBindingError("provider binding schema version drifted")
        object.__setattr__(
            self,
            "operation_id",
            _canonical_text(self.operation_id, "operation_id", maximum=512),
        )
        object.__setattr__(
            self,
            "execution_id",
            _canonical_text(self.execution_id, "execution_id", maximum=512),
        )
        object.__setattr__(
            self,
            "context_digest",
            _sha256(self.context_digest, "context_digest"),
        )
        values = tuple(self.receipt_ref_hashes)
        if len(values) != self.receipt_count:
            raise LiveEvidenceBindingError("provider receipt count does not match binding")
        if not values:
            raise LiveEvidenceBindingError("provider receipt set must not be empty")
        if len(set(values)) != len(values):
            raise LiveEvidenceBindingError("provider receipt hashes must be unique")
        for value in values:
            _sha256(value, "provider_receipt_ref_hash")
        object.__setattr__(self, "receipt_ref_hashes", tuple(sorted(values)))
        if (
            isinstance(self.receipt_count, bool)
            or not isinstance(self.receipt_count, int)
            or self.receipt_count < 1
        ):
            raise LiveEvidenceBindingError("receipt_count must be positive integer")
        if self.authority_scope != "provider-receipt-set-binding-only":
            raise LiveEvidenceBindingError("provider receipt binding authority escalated")
        if self.production_authority is not False:
            raise LiveEvidenceBindingError("provider receipt binding cannot execute inference")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "operation_id": self.operation_id,
            "execution_id": self.execution_id,
            "context_digest": self.context_digest,
            "receipt_ref_hashes": list(self.receipt_ref_hashes),
            "receipt_count": self.receipt_count,
            "authority_scope": self.authority_scope,
            "production_authority": self.production_authority,
        }

    @property
    def digest(self) -> str:
        return digest_json(self.as_dict())

    @property
    def reference(self) -> str:
        return "provider-set-sha256:" + self.digest


def bind_provider_receipt_set(
    *,
    operation_id: str,
    execution_id: str,
    context_digest: str,
    provider_receipts: Sequence[str] | Iterable[str],
) -> ProviderReceiptSetBinding:
    """Bind the complete provider receipt set without copying receipt payloads."""

    operation = _canonical_text(operation_id, "operation_id", maximum=512)
    execution = _canonical_text(execution_id, "execution_id", maximum=512)
    context = _sha256(context_digest, "context_digest")
    refs = _normalized_refs(
        provider_receipts,
        "provider_receipt",
        required_prefix="provider:",
        maximum_count=256,
    )
    if not refs:
        raise LiveEvidenceBindingError("provider_receipts must not be empty")
    return ProviderReceiptSetBinding(
        operation_id=operation,
        execution_id=execution,
        context_digest=context,
        receipt_ref_hashes=tuple(_hash_ref(value) for value in refs),
        receipt_count=len(refs),
    )


@dataclass(frozen=True, slots=True)
class GovernedAttachmentBinding:
    """Durable-reference binding for an admitted attachment."""

    attachment_id: str
    content_ref: str
    source_digest: str
    artifact_ref: str
    governance_receipt_ref_hash: str
    admission_digest: str
    policy_digest: str
    data_class: str
    byte_size: int
    extraction_receipt_ref_hash: str | None = None
    schema_version: int = LIVE_EVIDENCE_SCHEMA_VERSION
    authority_scope: str = "governed-attachment-binding-only"
    production_authority: bool = False

    def __post_init__(self) -> None:
        if self.schema_version != LIVE_EVIDENCE_SCHEMA_VERSION:
            raise LiveEvidenceBindingError("attachment binding schema version drifted")
        for field, maximum in (
            ("attachment_id", 512),
            ("content_ref", 2048),
            ("artifact_ref", 2048),
            ("data_class", 128),
        ):
            object.__setattr__(
                self,
                field,
                _canonical_text(getattr(self, field), field, maximum=maximum),
            )
        if not self.content_ref.startswith("attachment-sha256:"):
            raise LiveEvidenceBindingError(
                "attachment content_ref must be content-addressed"
            )
        if not (
            self.artifact_ref.startswith("artifact:")
            or self.artifact_ref.startswith("artifact-sha256:")
        ):
            raise LiveEvidenceBindingError(
                "artifact_ref must identify canonical governed artifact storage"
            )
        for field in (
            "source_digest",
            "governance_receipt_ref_hash",
            "admission_digest",
            "policy_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        if self.extraction_receipt_ref_hash is not None:
            object.__setattr__(
                self,
                "extraction_receipt_ref_hash",
                _sha256(
                    self.extraction_receipt_ref_hash,
                    "extraction_receipt_ref_hash",
                ),
            )
        if (
            isinstance(self.byte_size, bool)
            or not isinstance(self.byte_size, int)
            or self.byte_size < 0
        ):
            raise LiveEvidenceBindingError("byte_size must be non-negative integer")
        if self.content_ref != "attachment-sha256:" + self.source_digest:
            raise LiveEvidenceBindingError(
                "attachment content_ref does not match admitted source digest"
            )
        if self.authority_scope != "governed-attachment-binding-only":
            raise LiveEvidenceBindingError("attachment binding authority escalated")
        if self.production_authority is not False:
            raise LiveEvidenceBindingError("attachment binding cannot own storage")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "attachment_id": self.attachment_id,
            "content_ref": self.content_ref,
            "source_digest": self.source_digest,
            "artifact_ref": self.artifact_ref,
            "governance_receipt_ref_hash": self.governance_receipt_ref_hash,
            "admission_digest": self.admission_digest,
            "policy_digest": self.policy_digest,
            "data_class": self.data_class,
            "byte_size": self.byte_size,
            "extraction_receipt_ref_hash": self.extraction_receipt_ref_hash,
            "authority_scope": self.authority_scope,
            "production_authority": self.production_authority,
        }

    @property
    def digest(self) -> str:
        return digest_json(self.as_dict())

    @property
    def reference(self) -> str:
        return "chat-attachment-binding-sha256:" + self.digest


def bind_governed_attachment(
    reference: AttachmentReference,
    *,
    artifact_ref: str,
    governance_receipt_ref: str,
    extraction_receipt_ref: str | None = None,
) -> GovernedAttachmentBinding:
    """Replace an admitted upload payload with governed durable references."""

    if not isinstance(reference, AttachmentReference):
        raise TypeError("reference must be AttachmentReference")
    if not reference.ready_for_context:
        raise LiveEvidenceBindingError(
            "quarantined attachment cannot receive governed context binding"
        )
    canonical_artifact_ref = _canonical_text(
        artifact_ref,
        "artifact_ref",
        maximum=2048,
    )
    governance_ref = _canonical_text(
        governance_receipt_ref,
        "governance_receipt_ref",
        maximum=2048,
    )
    extraction_hash = None
    if extraction_receipt_ref is not None:
        extraction_hash = _hash_ref(
            _canonical_text(
                extraction_receipt_ref,
                "extraction_receipt_ref",
                maximum=2048,
            )
        )
    return GovernedAttachmentBinding(
        attachment_id=reference.attachment_id,
        content_ref=reference.content_ref,
        source_digest=reference.source_digest,
        artifact_ref=canonical_artifact_ref,
        governance_receipt_ref_hash=_hash_ref(governance_ref),
        admission_digest=reference.admission_digest,
        policy_digest=reference.policy_digest,
        data_class=reference.data_class,
        byte_size=reference.byte_size,
        extraction_receipt_ref_hash=extraction_hash,
    )


@dataclass(frozen=True, slots=True)
class LiveTurnEvidenceEnvelope:
    """One non-authoritative cross-plane evidence envelope for a chat turn."""

    operation_id: str
    request_digest: str
    turn_snapshot_digest: str
    context_digest: str
    provider_binding_digest: str | None = None
    tool_reconciliation_ref_hashes: tuple[str, ...] = ()
    attachment_binding_digests: tuple[str, ...] = ()
    claim_acceptance_digest: str | None = None
    schema_version: int = LIVE_EVIDENCE_SCHEMA_VERSION
    authority_scope: str = "live-turn-evidence-binding-only"
    production_authority: bool = False

    def __post_init__(self) -> None:
        if self.schema_version != LIVE_EVIDENCE_SCHEMA_VERSION:
            raise LiveEvidenceBindingError("live evidence schema version drifted")
        object.__setattr__(
            self,
            "operation_id",
            _canonical_text(self.operation_id, "operation_id", maximum=512),
        )
        for field in (
            "request_digest",
            "turn_snapshot_digest",
            "context_digest",
        ):
            object.__setattr__(self, field, _sha256(getattr(self, field), field))
        for field in ("provider_binding_digest", "claim_acceptance_digest"):
            value = getattr(self, field)
            if value is not None:
                object.__setattr__(self, field, _sha256(value, field))
        for field in (
            "tool_reconciliation_ref_hashes",
            "attachment_binding_digests",
        ):
            values = tuple(getattr(self, field))
            if len(set(values)) != len(values):
                raise LiveEvidenceBindingError(f"{field} must be unique")
            for value in values:
                _sha256(value, field)
            object.__setattr__(self, field, tuple(sorted(values)))
        if self.authority_scope != "live-turn-evidence-binding-only":
            raise LiveEvidenceBindingError("live evidence envelope authority escalated")
        if self.production_authority is not False:
            raise LiveEvidenceBindingError("live evidence envelope cannot commit state")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "operation_id": self.operation_id,
            "request_digest": self.request_digest,
            "turn_snapshot_digest": self.turn_snapshot_digest,
            "context_digest": self.context_digest,
            "provider_binding_digest": self.provider_binding_digest,
            "tool_reconciliation_ref_hashes": list(
                self.tool_reconciliation_ref_hashes
            ),
            "attachment_binding_digests": list(self.attachment_binding_digests),
            "claim_acceptance_digest": self.claim_acceptance_digest,
            "authority_scope": self.authority_scope,
            "production_authority": self.production_authority,
        }

    @property
    def digest(self) -> str:
        return digest_json(self.as_dict())

    @property
    def reference(self) -> str:
        return "chat-live-evidence-sha256:" + self.digest


def build_live_turn_evidence(
    snapshot: TurnSnapshot,
    *,
    context_digest: str,
    provider: ProviderReceiptSetBinding | None = None,
    tool_reconciliation_refs: Sequence[str] | Iterable[str] = (),
    attachments: Sequence[GovernedAttachmentBinding]
    | Iterable[GovernedAttachmentBinding] = (),
    claim_acceptance_digest: str | None = None,
) -> LiveTurnEvidenceEnvelope:
    """Bind cross-plane evidence to the exact durable turn snapshot."""

    if not isinstance(snapshot, TurnSnapshot):
        raise TypeError("snapshot must be TurnSnapshot")
    if snapshot.has_ambiguous_external_effect:
        raise LiveEvidenceBindingError(
            "ambiguous consequential tool effect must reconcile before evidence closure"
        )
    context = _sha256(context_digest, "context_digest")
    if provider is not None:
        if not isinstance(provider, ProviderReceiptSetBinding):
            raise TypeError("provider must be ProviderReceiptSetBinding")
        if provider.operation_id != snapshot.operation_id:
            raise LiveEvidenceBindingError(
                "provider receipt set belongs to another turn operation"
            )
        if provider.context_digest != context:
            raise LiveEvidenceBindingError(
                "provider receipt set context differs from turn context"
            )
    reconciliation_refs = _normalized_refs(
        tool_reconciliation_refs,
        "tool_reconciliation_ref",
        maximum_count=256,
    )
    attachment_values = tuple(attachments)
    if any(
        not isinstance(item, GovernedAttachmentBinding)
        for item in attachment_values
    ):
        raise TypeError("attachments must contain GovernedAttachmentBinding")
    attachment_digests = tuple(item.digest for item in attachment_values)
    if len(set(attachment_digests)) != len(attachment_digests):
        raise LiveEvidenceBindingError("duplicate governed attachment binding")
    claim_digest = (
        None
        if claim_acceptance_digest is None
        else _sha256(claim_acceptance_digest, "claim_acceptance_digest")
    )
    return LiveTurnEvidenceEnvelope(
        operation_id=snapshot.operation_id,
        request_digest=snapshot.request_digest,
        turn_snapshot_digest=operation_digest(snapshot),
        context_digest=context,
        provider_binding_digest=None if provider is None else provider.digest,
        tool_reconciliation_ref_hashes=tuple(
            _hash_ref(value) for value in reconciliation_refs
        ),
        attachment_binding_digests=attachment_digests,
        claim_acceptance_digest=claim_digest,
    )


__all__ = [
    "LIVE_EVIDENCE_SCHEMA_VERSION",
    "GovernedAttachmentBinding",
    "LiveEvidenceBindingError",
    "LiveTurnEvidenceEnvelope",
    "ProviderReceiptSetBinding",
    "bind_governed_attachment",
    "bind_provider_receipt_set",
    "build_live_turn_evidence",
]

"""Opt-in verified media intake without conferring instruction/model authority.

The canonical multimodal intake owns sanitization. The independently ported
media decoder measures and authenticates *bytes*; neither grants rights,
transcription, identity, semantic correctness or weight-promotion authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Mapping

from .contracts import Modality
from .intake import MultimodalAsset, MultimodalIntake
from .media_validation import (
    MediaValidationError,
    MediaValidationLimits,
    MediaValidationReceipt,
    validate_media,
)


@dataclass(frozen=True, slots=True)
class VerifiedMediaIntakeReceipt:
    """Two separately verifiable receipts bound to the identical source bytes."""

    asset: MultimodalAsset
    measured: MediaValidationReceipt
    source_digest: str
    evidence_digest: str
    authority_scope: str = "decoded-media-evidence-only"

    def __post_init__(self) -> None:
        if not isinstance(self.asset, MultimodalAsset) or not isinstance(
            self.measured, MediaValidationReceipt
        ):
            raise MediaValidationError("typed intake and decoder receipts required")
        if (
            self.authority_scope != "decoded-media-evidence-only"
            or self.source_digest != self.asset.content_digest
            or self.source_digest != self.measured.source_digest
            or self.asset.content_bytes != self.measured.source_bytes
        ):
            raise MediaValidationError("media source/decoder provenance does not match")
        expected = sha256(
            (
                "skeleton.verified-media-intake.v1\0"
                + self.asset.asset_id + "\0"
                + self.asset.modality.value + "\0"
                + self.source_digest + "\0"
                + self.measured.digest
            ).encode("utf-8")
        ).hexdigest()
        if self.evidence_digest != expected:
            raise MediaValidationError("verified intake digest mismatch")

    @property
    def instruction_trusted(self) -> bool:
        return False

    @property
    def training_authorized(self) -> bool:
        return False

    @property
    def promotion_authorized(self) -> bool:
        return False

    @property
    def measured_metadata(self) -> Mapping[str, object]:
        # Only decoder-derived metadata is measured. Untrusted caller
        # metadata remains separately sanitized on the original asset.
        return self.measured.measured_metadata


def verify_media_intake(
    *,
    asset_id: str,
    modality: Modality,
    mime_type: str,
    payload: bytes,
    metadata: Mapping[str, object] | None = None,
    limits: MediaValidationLimits | None = None,
) -> VerifiedMediaIntakeReceipt:
    """Sanitize first; decode only supported images / PCM WAVE under strict caps."""
    if not isinstance(modality, Modality) or modality not in {
        Modality.IMAGE, Modality.AUDIO
    }:
        raise MediaValidationError("verified intake supports image and PCM WAVE audio only")
    if limits is None:
        limits = MediaValidationLimits()
    if not isinstance(limits, MediaValidationLimits):
        raise MediaValidationError("typed media validation limits required")
    caps = limits.max_image_bytes if modality is Modality.IMAGE else limits.max_audio_bytes
    canonical = MultimodalIntake(max_payload_bytes=caps).sanitize(
        asset_id=asset_id,
        modality=modality,
        mime_type=mime_type,
        payload=payload,
        metadata=metadata,
    )
    # Strict format checks do not accept MIME aliases or multimodal payloads
    # whose byte format is incongruent with the sanitized MIME label.
    if canonical.mime_type not in (
        {"image/png", "image/jpeg", "image/webp"}
        if modality is Modality.IMAGE else {"audio/wav"}
    ):
        raise MediaValidationError("verified intake MIME is unsupported")
    measurement = validate_media(
        payload,
        modality=modality.value,
        mime_type=canonical.mime_type,
        limits=limits,
    )
    digest = sha256(
        (
            "skeleton.verified-media-intake.v1\0"
            + canonical.asset_id + "\0"
            + modality.value + "\0"
            + canonical.content_digest + "\0"
            + measurement.digest
        ).encode("utf-8")
    ).hexdigest()
    return VerifiedMediaIntakeReceipt(
        asset=canonical,
        measured=measurement,
        source_digest=canonical.content_digest,
        evidence_digest=digest,
    )

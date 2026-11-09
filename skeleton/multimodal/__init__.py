"""Multimodal intelligence contracts and fail-closed intake."""

from .contracts import (
    CrossModalReference,
    MediaArtifact,
    MediaError,
    MediaProvenance,
    Modality,
    ModalitySegment,
)
from .ingest import IngestionReceipt, MAX_INPUTS, MediaInput, ingest_media
from .intake import (
    MAX_INTAKE_BYTES,
    MultimodalAsset,
    MultimodalIntake,
    MultimodalSanitizationError,
)
from .sanitize import MAX_PAYLOAD_BYTES, SanitizationReceipt, sanitize_payload

__all__ = [
    "CrossModalReference",
    "IngestionReceipt",
    "MAX_INPUTS",
    "MAX_INTAKE_BYTES",
    "MAX_PAYLOAD_BYTES",
    "MediaArtifact",
    "MediaError",
    "MediaInput",
    "MediaProvenance",
    "Modality",
    "ModalitySegment",
    "MultimodalAsset",
    "MultimodalIntake",
    "MultimodalSanitizationError",
    "SanitizationReceipt",
    "ingest_media",
    "sanitize_payload",
]

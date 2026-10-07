"""Fail-closed compatibility intake for untrusted multimodal payloads."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from types import MappingProxyType
from typing import Mapping

from .contracts import MediaError, Modality

MAX_INTAKE_BYTES = 64 * 1024 * 1024
_ALLOWED_METADATA = frozenset({"filename", "language", "page", "duration_ms", "width", "height", "codec"})
_INSTRUCTION_MARKERS = (
    "ignore previous instructions",
    "ignore all previous instructions",
    "ignore prior instructions",
    "system prompt",
    "developer prompt",
    "reveal system prompt",
    "expose system prompt",
    "disable safety",
    "bypass guardrails",
)

@dataclass(frozen=True, slots=True)
class SanitizedMediaAsset:
    asset_id: str
    modality: Modality
    mime_type: str
    content_digest: str
    sanitized_metadata: Mapping[str, str]
    instruction_trusted: bool
    embedded_instruction_detected: bool

    def __post_init__(self) -> None:
        if not isinstance(self.asset_id, str) or not self.asset_id or self.asset_id != self.asset_id.strip():
            raise MediaError("invalid asset_id")
        if not isinstance(self.modality, Modality):
            raise MediaError("invalid modality")
        if not isinstance(self.mime_type, str) or not self.mime_type or self.mime_type != self.mime_type.strip():
            raise MediaError("invalid mime_type")
        if self.instruction_trusted is not False:
            raise MediaError("embedded media instructions may never be trusted")

class MultimodalIntake:
    """Normalize untrusted media without granting instruction authority."""

    def sanitize(
        self,
        *,
        asset_id: str,
        modality: Modality,
        mime_type: str,
        payload: bytes,
        metadata: Mapping[str, str] | None = None,
    ) -> SanitizedMediaAsset:
        if not isinstance(payload, bytes) or len(payload) > MAX_INTAKE_BYTES:
            raise MediaError("invalid or over-budget payload")
        raw_metadata = {} if metadata is None else metadata
        if not isinstance(raw_metadata, Mapping) or len(raw_metadata) > 128:
            raise MediaError("metadata budget exceeded")
        clean: dict[str, str] = {}
        for key, value in raw_metadata.items():
            if key not in _ALLOWED_METADATA:
                continue
            if not isinstance(value, str) or len(value) > 2048:
                raise MediaError("invalid metadata value")
            clean[key] = value
        text = payload.decode("utf-8", errors="ignore").casefold()
        detected = any(marker in text for marker in _INSTRUCTION_MARKERS)
        return SanitizedMediaAsset(
            asset_id=asset_id,
            modality=modality,
            mime_type=mime_type,
            content_digest=sha256(payload).hexdigest(),
            sanitized_metadata=MappingProxyType(dict(sorted(clean.items()))),
            instruction_trusted=False,
            embedded_instruction_detected=detected,
        )

"""Compatibility intake surface over the canonical multimodal sanitizer.

This module does not create a second execution authority. It adapts the bounded
sanitization contract into the asset shape consumed by the P3 learning
foundation while preserving original content identity as provenance evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import math
import re
from types import MappingProxyType
from typing import Mapping

from .contracts import MediaError, Modality
from .sanitize import MAX_PAYLOAD_BYTES, sanitize_payload

_MAX_METADATA_ITEMS = 128
_MAX_METADATA_KEY = 128
_MAX_METADATA_VALUE = 2048
_BLOCKED_METADATA = re.compile(
    r"(?i)(?:^|[_-])(?:system|developer|instruction|prompt|authorization|"
    r"api[_-]?key|secret|token|cookie)(?:$|[_-])"
)


class MultimodalSanitizationError(ValueError):
    """Raised when untrusted media cannot be admitted safely."""


def _text(name: str, value: object, *, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise MultimodalSanitizationError(f"invalid {name}")
    if len(value) > maximum:
        raise MultimodalSanitizationError(f"{name} exceeds {maximum} characters")
    return value


def _safe_metadata(metadata: Mapping[str, object] | None) -> Mapping[str, object]:
    if metadata is None:
        return MappingProxyType({})
    if not isinstance(metadata, Mapping) or len(metadata) > _MAX_METADATA_ITEMS:
        raise MultimodalSanitizationError("metadata budget exceeded")

    clean: dict[str, object] = {}
    for raw_key, raw_value in metadata.items():
        key = _text("metadata key", raw_key, maximum=_MAX_METADATA_KEY)
        if _BLOCKED_METADATA.search(key):
            continue
        if isinstance(raw_value, bool) or raw_value is None:
            value: object = raw_value
        elif isinstance(raw_value, int):
            value = raw_value
        elif isinstance(raw_value, float):
            if not math.isfinite(raw_value):
                raise MultimodalSanitizationError("metadata float must be finite")
            value = raw_value
        elif isinstance(raw_value, str):
            if len(raw_value) > _MAX_METADATA_VALUE:
                raise MultimodalSanitizationError("metadata value exceeds byte budget")
            value = raw_value
        else:
            # Nested/untyped structures are deliberately withheld from the
            # learning surface. Their raw bytes remain bound by content_digest.
            continue
        clean[key] = value
    return MappingProxyType(dict(sorted(clean.items())))


@dataclass(frozen=True, slots=True)
class MultimodalAsset:
    asset_id: str
    modality: Modality
    mime_type: str
    content_digest: str
    sanitized_metadata: Mapping[str, object]
    embedded_instruction_detected: bool
    instruction_trusted: bool = False
    authority_scope: str = "untrusted-media-evidence"

    def __post_init__(self) -> None:
        _text("asset_id", self.asset_id, maximum=512)
        if not isinstance(self.modality, Modality):
            raise MultimodalSanitizationError("typed modality required")
        object.__setattr__(
            self,
            "mime_type",
            _text("mime_type", self.mime_type, maximum=255).lower(),
        )
        if (
            not isinstance(self.content_digest, str)
            or len(self.content_digest) != 64
            or any(ch not in "0123456789abcdef" for ch in self.content_digest)
        ):
            raise MultimodalSanitizationError("invalid content_digest")
        if not isinstance(self.embedded_instruction_detected, bool):
            raise MultimodalSanitizationError(
                "embedded_instruction_detected must be bool"
            )
        if self.instruction_trusted is not False:
            raise MultimodalSanitizationError("instruction_trusted must remain false")
        if self.authority_scope != "untrusted-media-evidence":
            raise MultimodalSanitizationError("multimodal intake cannot grant authority")


class MultimodalIntake:
    """Bounded intake adapter that preserves source identity and strips authority."""

    def sanitize(
        self,
        *,
        asset_id: str,
        modality: Modality,
        mime_type: str,
        payload: bytes,
        metadata: Mapping[str, object] | None = None,
    ) -> MultimodalAsset:
        identity = _text("asset_id", asset_id, maximum=512)
        media_type = _text("mime_type", mime_type, maximum=255).lower()
        if not isinstance(modality, Modality):
            raise MultimodalSanitizationError("typed modality required")
        if not isinstance(payload, bytes):
            raise MultimodalSanitizationError("payload must be bytes")
        if len(payload) > MAX_PAYLOAD_BYTES:
            raise MultimodalSanitizationError("payload budget exceeded")

        # Instruction-like text is evidence only. It is surfaced as a flag and
        # never promoted into policy or execution authority.
        decoded = payload.decode("utf-8", errors="ignore")
        text_evidence = decoded if decoded else None
        active_content = media_type in {
            "application/javascript",
            "image/svg+xml",
            "text/html",
            "text/javascript",
        }
        try:
            _segment, receipt = sanitize_payload(
                segment_id=identity,
                modality=modality,
                payload=payload,
                source_id=identity,
                text=text_evidence,
                active_content=active_content,
            )
        except MediaError as exc:
            raise MultimodalSanitizationError(str(exc)) from exc

        safe_metadata = dict(_safe_metadata(metadata))
        safe_metadata["sanitization_policy_id"] = receipt.policy_id
        safe_metadata["sanitization_quarantined"] = receipt.quarantined
        if receipt.reason is not None:
            safe_metadata["sanitization_reason"] = receipt.reason

        source_digest = sha256(payload).hexdigest()
        if source_digest != receipt.source_digest:
            raise MultimodalSanitizationError("source digest drift")

        return MultimodalAsset(
            asset_id=identity,
            modality=modality,
            mime_type=media_type,
            content_digest=source_digest,
            sanitized_metadata=MappingProxyType(dict(sorted(safe_metadata.items()))),
            embedded_instruction_detected=receipt.reason == "embedded-instruction",
        )


__all__ = [
    "Modality",
    "MultimodalAsset",
    "MultimodalIntake",
    "MultimodalSanitizationError",
]

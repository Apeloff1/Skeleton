"""Bounded, fail-closed intake for untrusted multimodal assets.

This layer preserves content identity and provenance while stripping metadata
fields that could be mistaken for instruction or policy authority. It never
executes media, follows embedded instructions, or grants production authority.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from hashlib import sha256
from types import MappingProxyType

from .contracts import Modality
from .media_validation import (
    MediaValidationError,
    MediaValidationLimits,
    MediaValidationReceipt,
    validate_media,
)

MAX_INTAKE_BYTES = 512 * 1024 * 1024
MAX_METADATA_ITEMS = 128
MAX_METADATA_KEY_CHARS = 128
MAX_METADATA_VALUE_CHARS = 4096

_INSTRUCTION_PATTERN = re.compile(
    r"(?i)\b("
    r"ignore\s+(?:all\s+)?previous\s+instructions?"
    r"|system\s+prompt"
    r"|developer\s+message"
    r"|follow\s+(?:these|the)\s+instructions?"
    r"|override\s+(?:the\s+)?(?:system|developer|policy)"
    r")\b"
)
_AUTHORITY_METADATA_KEYS = frozenset(
    {
        "authority",
        "developer_message",
        "developer_prompt",
        "instruction",
        "instructions",
        "policy",
        "prompt",
        "role",
        "system",
        "system_message",
        "system_prompt",
        "tool_authority",
    }
)
_SAFE_METADATA_KEYS = frozenset(
    {
        "channels",
        "codec",
        "container",
        "duration_ms",
        "filename",
        "frame_rate",
        "height",
        "language",
        "orientation",
        "page_count",
        "sample_rate_hz",
        "source_id",
        "timestamp",
        "width",
    }
)
_MEDIA_PREFIX = {
    Modality.DOCUMENT: ("text/", "application/"),
    Modality.IMAGE: ("image/",),
    Modality.AUDIO: ("audio/",),
    Modality.SPEECH: ("audio/",),
    Modality.VIDEO: ("video/",),
}


class MultimodalSanitizationError(ValueError):
    """Multimodal input cannot be represented safely and deterministically."""


def _text(name: str, value: object, *, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MultimodalSanitizationError(f"{name} must be non-empty text")
    normalized = value.strip()
    if normalized != value or len(normalized) > maximum or "\x00" in normalized:
        raise MultimodalSanitizationError(f"{name} is not canonical bounded text")
    return normalized


def _metadata_value(value: object) -> object:
    if value is None or isinstance(value, (bool, int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            raise MultimodalSanitizationError("metadata contains non-finite numeric value")
        return value
    if isinstance(value, str):
        if len(value) > MAX_METADATA_VALUE_CHARS or "\x00" in value:
            raise MultimodalSanitizationError("metadata text exceeds intake bounds")
        return value
    if isinstance(value, (list, tuple)):
        if len(value) > MAX_METADATA_ITEMS:
            raise MultimodalSanitizationError("metadata sequence exceeds intake bounds")
        return [_metadata_value(item) for item in value]
    if isinstance(value, Mapping):
        return _sanitize_metadata(value)
    raise MultimodalSanitizationError("metadata contains unsupported value type")


def _sanitize_metadata(metadata: Mapping[str, object]) -> dict[str, object]:
    if len(metadata) > MAX_METADATA_ITEMS:
        raise MultimodalSanitizationError("metadata item budget exceeded")
    result: dict[str, object] = {}
    for raw_key, raw_value in metadata.items():
        key = _text("metadata key", raw_key, maximum=MAX_METADATA_KEY_CHARS)
        normalized_key = key.casefold()
        if normalized_key in _AUTHORITY_METADATA_KEYS:
            continue
        if normalized_key not in _SAFE_METADATA_KEYS:
            continue
        result[normalized_key] = _metadata_value(raw_value)
    try:
        json.dumps(
            result,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise MultimodalSanitizationError("sanitized metadata is not deterministic JSON") from exc
    return dict(sorted(result.items()))


def _detect_embedded_instruction(
    payload: bytes,
    metadata: Mapping[str, object],
) -> bool:
    sample = payload[: min(len(payload), 2 * 1024 * 1024)]
    decoded = sample.decode("utf-8", errors="ignore")
    if _INSTRUCTION_PATTERN.search(decoded):
        return True
    for key, value in metadata.items():
        if str(key).casefold() in _AUTHORITY_METADATA_KEYS:
            return True
        if isinstance(value, str) and _INSTRUCTION_PATTERN.search(value):
            return True
    return False


@dataclass(frozen=True, slots=True)
class MultimodalAsset:
    asset_id: str
    modality: Modality
    mime_type: str
    content_digest: str
    content_bytes: int
    embedded_instruction_detected: bool
    sanitized_metadata: Mapping[str, object]
    authority_scope: str = "untrusted-multimodal-evidence"

    def __post_init__(self) -> None:
        _text("asset_id", self.asset_id, maximum=512)
        if not isinstance(self.modality, Modality):
            raise MultimodalSanitizationError("modality must be typed")
        _text("mime_type", self.mime_type, maximum=255)
        if (
            not isinstance(self.content_digest, str)
            or len(self.content_digest) != 64
            or any(ch not in "0123456789abcdef" for ch in self.content_digest)
        ):
            raise MultimodalSanitizationError("content_digest must be lowercase sha256")
        if (
            isinstance(self.content_bytes, bool)
            or not isinstance(self.content_bytes, int)
            or self.content_bytes < 1
            or self.content_bytes > MAX_INTAKE_BYTES
        ):
            raise MultimodalSanitizationError("content byte count is outside intake bounds")
        if not isinstance(self.embedded_instruction_detected, bool):
            raise MultimodalSanitizationError("embedded_instruction_detected must be boolean")
        if self.authority_scope != "untrusted-multimodal-evidence":
            raise MultimodalSanitizationError(
                "multimodal intake cannot grant instruction or policy authority"
            )
        object.__setattr__(
            self,
            "sanitized_metadata",
            MappingProxyType(dict(self.sanitized_metadata)),
        )

    @property
    def instruction_trusted(self) -> bool:
        """Multimodal content never gains instruction or policy authority."""

        return False

    @property
    def size_bytes(self) -> int:
        return self.content_bytes


class MultimodalIntake:
    """Bounded staging registry; publish only fully admitted source receipts."""

    def __init__(self, *, max_payload_bytes: int = MAX_INTAKE_BYTES, max_assets: int = 4096) -> None:
        if (
            isinstance(max_payload_bytes, bool)
            or not isinstance(max_payload_bytes, int)
            or not 1 <= max_payload_bytes <= MAX_INTAKE_BYTES
        ):
            raise MultimodalSanitizationError("max_payload_bytes must be a positive bounded integer")
        if isinstance(max_assets, bool) or not isinstance(max_assets, int) or not 1 <= max_assets <= 4096:
            raise MultimodalSanitizationError("max_assets must be an integer in [1, 4096]")
        self.max_payload_bytes = max_payload_bytes
        self.max_assets = max_assets
        self._assets: dict[str, MultimodalAsset] = {}

    def _candidate(self, *, asset_id, modality, mime_type, payload, metadata=None) -> MultimodalAsset:
        canonical_id = _text("asset_id", asset_id, maximum=512)
        if not isinstance(modality, Modality):
            raise MultimodalSanitizationError("modality must be typed")
        canonical_mime = _text("mime_type", mime_type, maximum=255).lower().split(";", 1)[0].strip()
        if not canonical_mime.startswith(_MEDIA_PREFIX[modality]):
            raise MultimodalSanitizationError("mime type does not match the declared modality")
        if not isinstance(payload, bytes) or not payload:
            raise MultimodalSanitizationError("payload must be non-empty bytes")
        if len(payload) > self.max_payload_bytes:
            raise MultimodalSanitizationError("payload exceeds intake byte budget")
        raw_metadata = {} if metadata is None else metadata
        if not isinstance(raw_metadata, Mapping):
            raise MultimodalSanitizationError("metadata must be a mapping")
        candidate = MultimodalAsset(
            asset_id=canonical_id,
            modality=modality,
            mime_type=canonical_mime,
            content_digest=sha256(payload).hexdigest(),
            content_bytes=len(payload),
            embedded_instruction_detected=_detect_embedded_instruction(payload, raw_metadata),
            sanitized_metadata=_sanitize_metadata(raw_metadata),
        )
        prior = self._assets.get(canonical_id)
        if prior is not None and any(
            getattr(prior, name) != getattr(candidate, name)
            for name in (
                "asset_id",
                "modality",
                "mime_type",
                "content_digest",
                "content_bytes",
                "embedded_instruction_detected",
                "sanitized_metadata",
                "authority_scope",
            )
        ):
            raise MultimodalSanitizationError("asset id already bound to different source semantics")
        if prior is None and len(self._assets) >= self.max_assets:
            raise MultimodalSanitizationError("asset registry capacity exceeded")
        return candidate

    def sanitize(self, *, asset_id, modality, mime_type, payload, metadata=None) -> MultimodalAsset:
        candidate = self._candidate(
            asset_id=asset_id,
            modality=modality,
            mime_type=mime_type,
            payload=payload,
            metadata=metadata,
        )
        prior = self._assets.get(candidate.asset_id)
        if prior is not None:
            return prior
        self._assets[candidate.asset_id] = candidate
        return candidate

    def sanitize_verified(
        self,
        *,
        asset_id,
        modality,
        mime_type,
        payload,
        metadata=None,
        limits: MediaValidationLimits | None = None,
    ) -> VerifiedMultimodalAsset:
        candidate = self._candidate(
            asset_id=asset_id,
            modality=modality,
            mime_type=mime_type,
            payload=payload,
            metadata=metadata,
        )
        try:
            measurement = validate_media(
                payload,
                modality=modality.value,
                mime_type=candidate.mime_type,
                limits=limits,
            )
        except MediaValidationError as exc:
            raise MultimodalSanitizationError(str(exc)) from exc
        verified = VerifiedMultimodalAsset(
            asset_id=candidate.asset_id,
            modality=candidate.modality,
            mime_type=candidate.mime_type,
            content_digest=candidate.content_digest,
            content_bytes=candidate.content_bytes,
            embedded_instruction_detected=candidate.embedded_instruction_detected,
            sanitized_metadata=candidate.sanitized_metadata,
            validation=measurement,
        )
        prior = self._assets.get(candidate.asset_id)
        if isinstance(prior, VerifiedMultimodalAsset):
            if prior.validation.as_dict() != measurement.as_dict():
                raise MultimodalSanitizationError("asset id already bound to different decoder evidence")
            return prior
        self._assets[candidate.asset_id] = verified
        return verified

    def verify_verified_asset(self, asset: VerifiedMultimodalAsset, source: bytes) -> None:
        if self._assets.get(getattr(asset, "asset_id", None)) is not asset:
            raise MultimodalSanitizationError("verified asset was not issued by this intake")
        verify_verified_asset(asset, source)

    def safe_sanitize(self, **kwargs) -> MultimodalAsset:
        try:
            return self.sanitize(**kwargs)
        except MultimodalSanitizationError:
            raise
        except (TypeError, ValueError, KeyError) as exc:
            raise MultimodalSanitizationError("invalid intake request") from exc

    def safe_sanitize_verified(self, **kwargs) -> VerifiedMultimodalAsset:
        try:
            return self.sanitize_verified(**kwargs)
        except MultimodalSanitizationError:
            raise
        except (TypeError, ValueError, KeyError) as exc:
            raise MultimodalSanitizationError("invalid verified intake request") from exc


@dataclass(frozen=True, slots=True)
class VerifiedMultimodalAsset(MultimodalAsset):
    """Actual decoded-media evidence; instruction and training rights stay separate."""

    validation: MediaValidationReceipt = field(kw_only=True)

    def __post_init__(self) -> None:
        MultimodalAsset.__post_init__(self)
        if not isinstance(self.validation, MediaValidationReceipt):
            raise MultimodalSanitizationError("actual media decoder receipt is required")
        if (
            self.validation.source_digest != self.content_digest
            or self.validation.source_bytes != self.content_bytes
            or self.validation.media_type != self.mime_type
            or self.modality not in {Modality.IMAGE, Modality.AUDIO}
        ):
            raise MultimodalSanitizationError("decoder receipt and source identity differ")


def verify_verified_asset(asset: VerifiedMultimodalAsset, source: bytes) -> None:
    if not isinstance(asset, VerifiedMultimodalAsset):
        raise MultimodalSanitizationError("typed verified asset is required")
    if not isinstance(source, bytes) or len(source) != asset.content_bytes:
        raise MultimodalSanitizationError("source bytes differ from issued evidence")
    if sha256(source).hexdigest() != asset.content_digest:
        raise MultimodalSanitizationError("source content digest mismatch")
    try:
        measured = validate_media(
            source,
            modality=asset.modality.value,
            mime_type=asset.mime_type,
            limits=asset.validation.limits,
        )
    except (MediaValidationError, AttributeError, TypeError) as exc:
        raise MultimodalSanitizationError("verified source cannot be decoded") from exc
    if measured.as_dict() != asset.validation.as_dict() or asset.instruction_trusted:
        raise MultimodalSanitizationError("actual decoded source differs from issued evidence")


_INSTRUCTION_PATTERNS = (re.compile(_INSTRUCTION_PATTERN.pattern.encode()),)
ValidationEvidence = MediaValidationReceipt

__all__ = [
    "MAX_INTAKE_BYTES",
    "MultimodalAsset",
    "MultimodalIntake",
    "MultimodalSanitizationError",
    "ValidationEvidence",
    "VerifiedMultimodalAsset",
    "verify_verified_asset",
]

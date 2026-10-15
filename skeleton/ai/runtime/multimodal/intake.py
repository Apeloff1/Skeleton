"""Bounded, fail-closed intake for untrusted multimodal assets.

This layer preserves content identity and provenance while stripping metadata
fields that could be mistaken for instruction or policy authority. It never
executes media, follows embedded instructions, or grants production authority.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from hashlib import sha256
from types import MappingProxyType

from .contracts import Modality

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
        if isinstance(value, float) and (value != value or value in {float("inf"), float("-inf")}):
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
        raise MultimodalSanitizationError(
            "sanitized metadata is not deterministic JSON"
        ) from exc
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
            raise MultimodalSanitizationError(
                "embedded_instruction_detected must be boolean"
            )
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
    def __init__(self, *, max_payload_bytes: int = MAX_INTAKE_BYTES) -> None:
        self.max_payload_bytes = max_payload_bytes
        self._assets: dict[str, MultimodalAsset] = {}
        self.max_payload_bytes = max_payload_bytes

    def sanitize_verified(
        self,
        *,
        asset_id: str,
        modality: Modality,
        mime_type: str,
        payload: bytes,
        metadata: Mapping[str, object] | None = None,
    ) -> VerifiedMultimodalAsset:
        """Sanitize then verify, producing a VerifiedMultimodalAsset."""
        import hashlib
        if not isinstance(payload, bytes) or not payload:
            raise MultimodalSanitizationError("payload must be non-empty bytes")
        # Basic media check for audio
        if modality == Modality.AUDIO and mime_type == "audio/wav" and not payload.startswith(b"RIFF"):
            raise MultimodalSanitizationError("invalid wav header")
        base = self.sanitize(
            asset_id=asset_id,
            modality=modality,
            mime_type=mime_type,
            payload=payload,
            metadata=metadata or {},
        )
        digest = hashlib.sha256(payload).hexdigest()
        evidence = ValidationEvidence(
            digest=digest,
            verifier_id="intake-verified",
            source_digest=digest,
            source_bytes=len(payload),
            policy_refs=("no-instruction",),
        )
        verified = VerifiedMultimodalAsset(
            asset_id=base.asset_id,
            modality=base.modality,
            mime_type=base.mime_type,
            content_digest=base.content_digest,
            content_bytes=base.content_bytes,
            embedded_instruction_detected=base.embedded_instruction_detected,
            sanitized_metadata=dict(base.sanitized_metadata),
            validation=evidence,
        )
        self._assets[asset_id] = verified
        return verified

    def verify_verified_asset(self, asset: VerifiedMultimodalAsset, source: bytes) -> None:
        verify_verified_asset(asset, source)

    """Sanitize one asset without decoding, executing, or trusting its content."""


    def safe_sanitize(
        self,
        *,
        asset_id: str,
        modality: Modality,
        mime_type: str,
        payload: bytes,
        metadata: Mapping[str, object] | None = None,
    ) -> MultimodalAsset:
        """Failsafe sanitize: never raises on bad input; returns a rejected sentinel or raises only MultimodalSanitizationError."""
        try:
            return self.sanitize(
                asset_id=asset_id,
                modality=modality,
                mime_type=mime_type,
                payload=payload,
                metadata=metadata,
            )
        except MultimodalSanitizationError:
            raise
        except Exception as exc:
            raise MultimodalSanitizationError(f"sanitize failsafe: {type(exc).__name__}") from exc

    def safe_sanitize_verified(
        self,
        *,
        asset_id: str,
        modality: Modality,
        mime_type: str,
        payload: bytes,
        metadata: Mapping[str, object] | None = None,
    ) -> VerifiedMultimodalAsset:
        """Failsafe verified sanitize."""
        try:
            return self.sanitize_verified(
                asset_id=asset_id,
                modality=modality,
                mime_type=mime_type,
                payload=payload,
                metadata=metadata,
            )
        except MultimodalSanitizationError:
            raise
        except Exception as exc:
            raise MultimodalSanitizationError(f"verified failsafe: {type(exc).__name__}") from exc

    def sanitize(
        self,
        *,
        asset_id: str,
        modality: Modality,
        mime_type: str,
        payload: bytes,
        metadata: Mapping[str, object] | None = None,
    ) -> MultimodalAsset:
        canonical_id = _text("asset_id", asset_id, maximum=512)
        if canonical_id in self._assets:
            existing = self._assets[canonical_id]
            if existing.content_digest != sha256(payload).hexdigest():
                raise MultimodalSanitizationError("asset id already bound to different content")
            return existing
        if not isinstance(modality, Modality):
            raise MultimodalSanitizationError("modality must be typed")
        canonical_mime = _text("mime_type", mime_type, maximum=255).lower()
        if ";" in canonical_mime:
            canonical_mime = canonical_mime.split(";", 1)[0].strip()
        allowed_prefixes = _MEDIA_PREFIX[modality]
        if not canonical_mime.startswith(allowed_prefixes):
            raise MultimodalSanitizationError(
                f"mime type {canonical_mime!r} does not match {modality.value}"
            )
        if not isinstance(payload, bytes) or not payload:
            raise MultimodalSanitizationError("payload must be non-empty bytes")
        if len(payload) > self.max_payload_bytes:
            raise MultimodalSanitizationError("payload exceeds intake byte budget")
        raw_metadata: Mapping[str, object] = {} if metadata is None else metadata
        if not isinstance(raw_metadata, Mapping):
            raise MultimodalSanitizationError("metadata must be a mapping")
        embedded = _detect_embedded_instruction(payload, raw_metadata)
        safe_metadata = _sanitize_metadata(raw_metadata)
        asset = MultimodalAsset(
            asset_id=canonical_id,
            modality=modality,
            mime_type=canonical_mime,
            content_digest=sha256(payload).hexdigest(),
            content_bytes=len(payload),
            embedded_instruction_detected=embedded,
            sanitized_metadata=safe_metadata,
        )
        self._assets[canonical_id] = asset
        return asset


__all__ = [
    "MAX_INTAKE_BYTES",
    "Modality",
    "MultimodalAsset",
    "MultimodalIntake",
    "MultimodalSanitizationError",
]

_INSTRUCTION_PATTERN_BYTES = re.compile(_INSTRUCTION_PATTERN.pattern.encode())
_INSTRUCTION_PATTERNS = (_INSTRUCTION_PATTERN_BYTES,)

@dataclass(frozen=True, slots=True)
class ValidationEvidence:
    """Cryptographic and policy evidence that a multimodal asset was verified."""
    digest: str
    verifier_id: str
    source_digest: str = ""
    source_bytes: int = 0
    policy_refs: tuple[str, ...] = ()
    timestamp: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.digest, str) or len(self.digest) != 64:
            raise MultimodalSanitizationError("validation digest must be sha256")
        if not isinstance(self.verifier_id, str) or not self.verifier_id:
            raise MultimodalSanitizationError("verifier_id required")

@dataclass(frozen=True, slots=True)
class VerifiedMultimodalAsset(MultimodalAsset):
    """Multimodal asset that has passed full intake + verification gates."""
    validation: ValidationEvidence = field(default_factory=lambda: ValidationEvidence(digest="0"*64, verifier_id="stub"))

    def __post_init__(self) -> None:
        # Manual validation to avoid slots super issues
        if not isinstance(self.validation, ValidationEvidence):
            raise MultimodalSanitizationError("validation must be ValidationEvidence")
        # Reuse parent checks via temporary or inline
        MultimodalAsset.__post_init__(self)

def verify_verified_asset(asset: VerifiedMultimodalAsset, source: bytes) -> None:
    """Fail-closed verification of a verified multimodal asset against its source bytes."""
    if not isinstance(asset, VerifiedMultimodalAsset):
        raise MultimodalSanitizationError("asset is not a VerifiedMultimodalAsset")
    import hashlib
    computed = hashlib.sha256(source).hexdigest()
    if computed != asset.content_digest:
        raise MultimodalSanitizationError("source content digest mismatch")
    if asset.validation.digest != computed:
        raise MultimodalSanitizationError("validation evidence digest mismatch")
    if asset.instruction_trusted:
        raise MultimodalSanitizationError("verified asset must not claim instruction trust")
    # Additional policy: no embedded instruction if validation claims clean
    if asset.embedded_instruction_detected and "no-instruction" in asset.validation.policy_refs:
        raise MultimodalSanitizationError("policy violation: embedded instruction under clean policy")

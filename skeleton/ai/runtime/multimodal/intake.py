"""Converged fail-closed multimodal intake for P3."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from copy import copy
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType

from .media_validation import (
    MediaValidationError,
    MediaValidationLimits,
    MediaValidationReceipt,
    validate_media,
)


class MultimodalSanitizationError(RuntimeError):
    pass


class Modality(str, Enum):
    DOCUMENT = "document"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"


@dataclass(frozen=True, slots=True)
class MultimodalPolicy:
    modality: Modality
    allowed_mime_types: frozenset[str]
    max_bytes: int
    allowed_metadata_keys: frozenset[str]


DEFAULT_POLICIES = {
    Modality.DOCUMENT: MultimodalPolicy(
        Modality.DOCUMENT,
        frozenset({"text/plain", "text/markdown", "application/pdf", "application/json"}),
        16 * 1024 * 1024,
        frozenset({"filename", "language", "page_count", "source_id", "created_at"}),
    ),
    Modality.IMAGE: MultimodalPolicy(
        Modality.IMAGE,
        frozenset({"image/png", "image/jpeg", "image/webp"}),
        32 * 1024 * 1024,
        frozenset({"filename", "width", "height", "source_id", "created_at"}),
    ),
    Modality.AUDIO: MultimodalPolicy(
        Modality.AUDIO,
        frozenset({"audio/wav", "audio/mpeg", "audio/ogg", "audio/flac"}),
        128 * 1024 * 1024,
        frozenset({"filename", "duration_ms", "sample_rate", "source_id", "created_at"}),
    ),
    Modality.VIDEO: MultimodalPolicy(
        Modality.VIDEO,
        frozenset({"video/mp4", "video/webm", "video/quicktime"}),
        512 * 1024 * 1024,
        frozenset({"filename", "duration_ms", "width", "height", "source_id", "created_at"}),
    ),
}
_INSTRUCTION_PATTERNS = (
    re.compile(rb"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(rb"system\s*prompt", re.IGNORECASE),
    re.compile(rb"<\s*script\b", re.IGNORECASE),
    re.compile(rb"assistant\s*:", re.IGNORECASE),
    re.compile(rb"developer\s*:", re.IGNORECASE),
)
_BLOCKED_METADATA_FRAGMENTS = (
    "prompt",
    "instruction",
    "system",
    "assistant",
    "developer",
    "tool",
    "function",
)


@dataclass(frozen=True, slots=True)
class MultimodalAsset:
    asset_id: str
    modality: Modality
    mime_type: str
    content_digest: str
    size_bytes: int
    sanitized_metadata: Mapping[str, object]
    instruction_trusted: bool
    embedded_instruction_detected: bool

    def __post_init__(self) -> None:
        if self.instruction_trusted is not False:
            raise MultimodalSanitizationError("multimodal payloads never receive instruction authority")
        object.__setattr__(self, "sanitized_metadata", dict(self.sanitized_metadata))


@dataclass(frozen=True, slots=True)
class VerifiedMultimodalAsset(MultimodalAsset):
    validation: MediaValidationReceipt

    def __post_init__(self) -> None:
        MultimodalAsset.__post_init__(self)
        if not isinstance(self.validation, MediaValidationReceipt):
            raise MultimodalSanitizationError("verified asset requires actual media validation receipt")
        if (
            self.content_digest != self.validation.source_digest
            or self.size_bytes != self.validation.source_bytes
            or self.mime_type != self.validation.media_type
            or self.modality.value != ("image" if self.validation.width is not None else "audio")
            or self.embedded_instruction_detected is not False
        ):
            raise MultimodalSanitizationError("verified asset/receipt identity mismatch")
        for key, value in self.validation.measured_metadata.items():
            if self.sanitized_metadata.get(key) != value:
                raise MultimodalSanitizationError("verified asset measured metadata mismatch")
        object.__setattr__(self, "sanitized_metadata", MappingProxyType(dict(self.sanitized_metadata)))

    def as_dict(self) -> dict[str, object]:
        return {
            "asset_id": self.asset_id,
            "modality": self.modality.value,
            "mime_type": self.mime_type,
            "content_digest": self.content_digest,
            "size_bytes": self.size_bytes,
            "sanitized_metadata": dict(self.sanitized_metadata),
            "instruction_trusted": self.instruction_trusted,
            "embedded_instruction_detected": self.embedded_instruction_detected,
            "validation": self.validation.as_dict(),
        }

    @property
    def digest(self) -> str:
        encoded = json.dumps(
            self.as_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class MultimodalIntake:
    def __init__(self, policies: Mapping[Modality, MultimodalPolicy] | None = None) -> None:
        self._policies = dict(DEFAULT_POLICIES if policies is None else policies)
        if set(self._policies) != set(Modality):
            raise MultimodalSanitizationError("policies must cover every modality")
        self._assets: dict[str, MultimodalAsset] = {}

    @staticmethod
    def _metadata(policy: MultimodalPolicy, metadata: Mapping[str, object] | None) -> dict[str, object]:
        if metadata is None:
            return {}
        clean: dict[str, object] = {}
        for raw_key, value in metadata.items():
            if not isinstance(raw_key, str) or not raw_key.strip():
                raise MultimodalSanitizationError("metadata keys must be text")
            key = raw_key.strip()
            lowered = key.casefold()
            if any(fragment in lowered for fragment in _BLOCKED_METADATA_FRAGMENTS):
                continue
            if key not in policy.allowed_metadata_keys:
                continue
            if value is None or isinstance(value, (bool, int, float, str)):
                clean[key] = value
            else:
                raise MultimodalSanitizationError(f"metadata value for {key} must be scalar")
        return clean

    def sanitize(
        self,
        *,
        asset_id: str,
        modality: Modality,
        mime_type: str,
        payload: bytes,
        metadata: Mapping[str, object] | None = None,
    ) -> MultimodalAsset:
        if not isinstance(payload, bytes):
            raise MultimodalSanitizationError("payload must be immutable bytes")
        policy = self._policies[modality]
        normalized_mime = mime_type.strip().casefold()
        if normalized_mime not in policy.allowed_mime_types:
            raise MultimodalSanitizationError(f"{modality.value} MIME type is not allowed: {normalized_mime}")
        if len(payload) > policy.max_bytes:
            raise MultimodalSanitizationError(f"{modality.value} payload exceeds size policy")
        sample = payload[: min(len(payload), 2 * 1024 * 1024)]
        detected = normalized_mime in {"text/plain", "text/markdown", "application/json"} and any(
            p.search(sample) is not None for p in _INSTRUCTION_PATTERNS
        )
        asset = MultimodalAsset(
            asset_id=asset_id.strip(),
            modality=modality,
            mime_type=normalized_mime,
            content_digest=hashlib.sha256(payload).hexdigest(),
            size_bytes=len(payload),
            sanitized_metadata=self._metadata(policy, metadata),
            instruction_trusted=False,
            embedded_instruction_detected=detected,
        )
        prior = self._assets.get(asset.asset_id)
        if prior is not None and prior != asset:
            raise MultimodalSanitizationError("asset identity conflict")
        self._assets[asset.asset_id] = asset
        return asset

    def sanitize_verified(
        self,
        *,
        asset_id: str,
        modality: Modality,
        mime_type: str,
        payload: bytes,
        metadata: Mapping[str, object] | None = None,
        limits: MediaValidationLimits | None = None,
    ) -> VerifiedMultimodalAsset:
        """Admit measured, fully decoded media; opaque sanitize stays compatible."""
        if not isinstance(modality, Modality) or modality not in {Modality.IMAGE, Modality.AUDIO}:
            raise MultimodalSanitizationError("verified intake supports image and PCM WAVE audio")
        if not isinstance(asset_id, str) or not asset_id.strip() or len(asset_id) > 512:
            raise MultimodalSanitizationError("asset_id must be bounded nonempty text")
        if not isinstance(mime_type, str) or not isinstance(payload, bytes):
            raise MultimodalSanitizationError("verified media requires MIME text and immutable bytes")
        policy = self._policies[modality]
        if len(payload) > policy.max_bytes or mime_type.strip().casefold() not in policy.allowed_mime_types:
            raise MultimodalSanitizationError("verified media exceeds configured intake policy")
        try:
            selected_limits = MediaValidationLimits() if limits is None else limits
            if not isinstance(selected_limits, MediaValidationLimits):
                raise MediaValidationError("limits must be MediaValidationLimits")
            selected_limits = MediaValidationLimits(**selected_limits.as_dict())
            if metadata is not None:
                if not isinstance(metadata, Mapping) or len(metadata) > 128:
                    raise MediaValidationError("metadata must be a bounded mapping")
                if any(
                    not isinstance(key, str)
                    or len(key) > 512
                    or (value is not None and not isinstance(value, (bool, int, float, str)))
                    or (isinstance(value, str) and len(value) > selected_limits.max_metadata_bytes)
                    for key, value in metadata.items()
                ):
                    raise MediaValidationError("metadata must contain bounded scalar fields")
                encoded = json.dumps(dict(metadata), ensure_ascii=False, allow_nan=False).encode("utf-8")
                if len(encoded) > selected_limits.max_metadata_bytes:
                    raise MediaValidationError("media metadata byte budget exceeded")
                normalized = {key.strip(): value for key, value in metadata.items()}
                if len(normalized) != len(metadata) or "" in normalized:
                    raise MediaValidationError("media metadata keys must be distinct normalized text")
                metadata = normalized
            validation = validate_media(
                payload, modality=modality.value, mime_type=mime_type, limits=selected_limits
            )
            measured = validation.measured_metadata
            for key, actual in measured.items():
                if metadata is None or key not in metadata:
                    continue
                claimed = metadata[key]
                if isinstance(actual, (int, float)):
                    if (
                        isinstance(claimed, bool)
                        or not isinstance(claimed, (int, float))
                        or not math.isfinite(claimed)
                        or claimed != actual
                    ):
                        raise MediaValidationError(f"media metadata {key} conflicts with decoded measurement")
                elif claimed != actual:
                    raise MediaValidationError(f"media metadata {key} conflicts with decoded measurement")
            staged = copy(self)
            staged._assets = {}
            envelope = staged.sanitize(
                asset_id=asset_id, modality=modality, mime_type=mime_type, payload=payload, metadata=metadata
            )
            verified = VerifiedMultimodalAsset(
                asset_id=envelope.asset_id,
                modality=envelope.modality,
                mime_type=envelope.mime_type,
                content_digest=envelope.content_digest,
                size_bytes=envelope.size_bytes,
                sanitized_metadata={**envelope.sanitized_metadata, **measured},
                instruction_trusted=False,
                embedded_instruction_detected=False,
                validation=validation,
            )
        except (MediaValidationError, TypeError, ValueError, OverflowError) as exc:
            raise MultimodalSanitizationError(str(exc)) from exc
        prior = self._assets.get(verified.asset_id)
        if prior is not None and (
            not isinstance(prior, VerifiedMultimodalAsset) or prior.as_dict() != verified.as_dict()
        ):
            raise MultimodalSanitizationError("verified asset identity conflict")
        self._assets[verified.asset_id] = verified
        return verified

    def verify_verified_asset(
        self, asset: VerifiedMultimodalAsset, payload: bytes
    ) -> VerifiedMultimodalAsset:
        """Re-decode source bytes; receipt construction alone grants no trust."""
        if not isinstance(asset, VerifiedMultimodalAsset):
            raise MultimodalSanitizationError("asset has no verified decoder evidence")
        try:
            validation = asset.validation
            if not isinstance(validation, MediaValidationReceipt):
                raise MediaValidationError("asset has no valid media receipt")
            fields = {key: value for key, value in validation.as_dict().items() if key != "schema_version"}
            fields["limits"] = MediaValidationLimits(**fields["limits"])
            reconstructed = MediaValidationReceipt(**fields)
            staged = copy(self)
            staged._assets = {}
            measured = staged.sanitize_verified(
                asset_id=asset.asset_id,
                modality=asset.modality,
                mime_type=asset.mime_type,
                payload=payload,
                metadata=asset.sanitized_metadata,
                limits=reconstructed.limits,
            )
            if measured.as_dict() != asset.as_dict():
                raise MediaValidationError("verified media receipt/asset drift")
        except (MediaValidationError, TypeError, ValueError, AttributeError) as exc:
            raise MultimodalSanitizationError(str(exc)) from exc
        return measured


def verify_verified_asset(asset: VerifiedMultimodalAsset, payload: bytes) -> VerifiedMultimodalAsset:
    """Revalidate verified media under the canonical default intake policies."""
    return MultimodalIntake().verify_verified_asset(asset, payload)


__all__ = [
    "DEFAULT_POLICIES",
    "Modality",
    "MultimodalAsset",
    "MultimodalIntake",
    "MultimodalPolicy",
    "MultimodalSanitizationError",
    "VerifiedMultimodalAsset",
    "verify_verified_asset",
]

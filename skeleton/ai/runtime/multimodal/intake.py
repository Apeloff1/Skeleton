"""Converged fail-closed multimodal intake for P3."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import re
from typing import Mapping


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
    Modality.DOCUMENT: MultimodalPolicy(Modality.DOCUMENT, frozenset({"text/plain", "text/markdown", "application/pdf", "application/json"}), 16 * 1024 * 1024, frozenset({"filename", "language", "page_count", "source_id", "created_at"})),
    Modality.IMAGE: MultimodalPolicy(Modality.IMAGE, frozenset({"image/png", "image/jpeg", "image/webp"}), 32 * 1024 * 1024, frozenset({"filename", "width", "height", "source_id", "created_at"})),
    Modality.AUDIO: MultimodalPolicy(Modality.AUDIO, frozenset({"audio/wav", "audio/mpeg", "audio/ogg", "audio/flac"}), 128 * 1024 * 1024, frozenset({"filename", "duration_ms", "sample_rate", "source_id", "created_at"})),
    Modality.VIDEO: MultimodalPolicy(Modality.VIDEO, frozenset({"video/mp4", "video/webm", "video/quicktime"}), 512 * 1024 * 1024, frozenset({"filename", "duration_ms", "width", "height", "source_id", "created_at"})),
}
_INSTRUCTION_PATTERNS = (
    re.compile(rb"ignore\s+(all\s+)?previous\s+instructions", re.I),
    re.compile(rb"system\s*prompt", re.I),
    re.compile(rb"<\s*script\b", re.I),
    re.compile(rb"assistant\s*:", re.I),
    re.compile(rb"developer\s*:", re.I),
)
_BLOCKED_METADATA_FRAGMENTS = ("prompt", "instruction", "system", "assistant", "developer", "tool", "function")


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
        detected = normalized_mime in {"text/plain", "text/markdown", "application/json"} and any(p.search(sample) is not None for p in _INSTRUCTION_PATTERNS)
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


__all__ = [
    "DEFAULT_POLICIES",
    "Modality",
    "MultimodalAsset",
    "MultimodalIntake",
    "MultimodalPolicy",
    "MultimodalSanitizationError",
]

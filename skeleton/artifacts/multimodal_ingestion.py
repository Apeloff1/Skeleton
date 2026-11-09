"""Governed pre-decode multimodal ingestion for VOL-153.

The codec/model layers are intentionally outside this module. The ingestion core
only admits content after byte, trust, classification and declared-resource
checks succeed, then binds the admitted content to a pre-registered modality
pipeline. Transformation lineage is content-addressed and append-only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
import re
from typing import Any, Mapping, Sequence

from skeleton.ai.runtime.extensions.multimodal import (
    MediaMetadata,
    MediaTransform,
    MultimodalAsset,
    ResourceLimits,
    digest_bytes,
)

_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:+/-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")


class IngestionError(ValueError):
    """Raised when a media object is not safe to admit."""


def _token(value: str, field_name: str) -> str:
    text = str(value).strip()
    if not _TOKEN.fullmatch(text):
        raise IngestionError(f"{field_name} must be a stable token")
    return text


def _digest_text(value: str, field_name: str) -> str:
    text = str(value).strip().lower()
    if not _DIGEST.fullmatch(text):
        raise IngestionError(f"{field_name} must be a lowercase sha256 digest")
    return text


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
        raise IngestionError("value is not canonically serializable") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _safe_metadata(
    values: Mapping[str, Any],
    *,
    allowlist: frozenset[str],
    max_value_chars: int,
) -> dict[str, str | int | float | bool | None]:
    safe: dict[str, str | int | float | bool | None] = {}
    for raw_key, raw_value in values.items():
        key = _token(raw_key, "metadata key")
        if key not in allowlist:
            raise IngestionError(f"metadata key {key!r} is not allowed")
        if isinstance(raw_value, bool) or raw_value is None:
            value = raw_value
        elif isinstance(raw_value, int):
            value = raw_value
        elif isinstance(raw_value, float):
            if not math.isfinite(raw_value):
                raise IngestionError(f"metadata value for {key!r} must be finite")
            value = raw_value
        elif isinstance(raw_value, str):
            if len(raw_value) > max_value_chars:
                raise IngestionError(f"metadata value for {key!r} exceeds size limit")
            value = raw_value
        else:
            raise IngestionError(
                f"metadata value for {key!r} must be a scalar, not {type(raw_value).__name__}"
            )
        safe[key] = value
    _canonical(safe)
    return safe


@dataclass(frozen=True, slots=True)
class MediaProbe:
    """Bounded container/header facts available before expensive decoding."""

    media_type: str
    format: str
    byte_size: int
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None
    fps: float | None = None
    sample_rate_hz: int | None = None
    channels: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "media_type", _token(self.media_type, "media_type"))
        object.__setattr__(self, "format", _token(self.format, "format"))
        if self.byte_size < 0:
            raise IngestionError("byte_size must be non-negative")
        if (self.width is None) != (self.height is None):
            raise IngestionError("width and height must be supplied together")
        if self.width is not None and (
            self.width <= 0 or self.height is None or self.height <= 0
        ):
            raise IngestionError("media dimensions must be positive")
        if self.duration_seconds is not None and (
            not math.isfinite(self.duration_seconds) or self.duration_seconds < 0
        ):
            raise IngestionError("duration_seconds must be finite and non-negative")
        if self.fps is not None and (not math.isfinite(self.fps) or self.fps <= 0):
            raise IngestionError("fps must be finite and positive")
        if self.sample_rate_hz is not None and self.sample_rate_hz <= 0:
            raise IngestionError("sample_rate_hz must be positive")
        if self.channels is not None and self.channels <= 0:
            raise IngestionError("channels must be positive")
        copied = dict(self.metadata)
        _canonical(copied)
        object.__setattr__(self, "metadata", copied)

    @property
    def pixels(self) -> int | None:
        if self.width is None or self.height is None:
            return None
        return self.width * self.height

    @property
    def estimated_frames(self) -> int | None:
        if self.duration_seconds is None or self.fps is None:
            return None
        return math.ceil(self.duration_seconds * self.fps)


@dataclass(frozen=True, slots=True)
class PipelineBinding:
    """Decode/inference route selected only after admission succeeds."""

    media_type: str
    pipeline_id: str
    accepted_formats: frozenset[str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "media_type", _token(self.media_type, "media_type"))
        object.__setattr__(self, "pipeline_id", _token(self.pipeline_id, "pipeline_id"))
        formats = frozenset(_token(v, "accepted format") for v in self.accepted_formats)
        if not formats:
            raise IngestionError("pipeline must accept at least one format")
        object.__setattr__(self, "accepted_formats", formats)


@dataclass(frozen=True, slots=True)
class IngestionPolicy:
    policy_id: str
    allowed_media_types: frozenset[str]
    allowed_trust_labels: frozenset[str]
    allowed_classifications: frozenset[str]
    metadata_allowlist: frozenset[str] = frozenset()
    limits: ResourceLimits = ResourceLimits()
    max_metadata_value_chars: int = 1024

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _token(self.policy_id, "policy_id"))
        for field_name in (
            "allowed_media_types",
            "allowed_trust_labels",
            "allowed_classifications",
            "metadata_allowlist",
        ):
            values = frozenset(_token(v, field_name) for v in getattr(self, field_name))
            if field_name != "metadata_allowlist" and not values:
                raise IngestionError(f"{field_name} must not be empty")
            object.__setattr__(self, field_name, values)
        if self.max_metadata_value_chars <= 0:
            raise IngestionError("max_metadata_value_chars must be positive")

    @property
    def digest(self) -> str:
        return _digest(
            {
                "policy_id": self.policy_id,
                "allowed_media_types": sorted(self.allowed_media_types),
                "allowed_trust_labels": sorted(self.allowed_trust_labels),
                "allowed_classifications": sorted(self.allowed_classifications),
                "metadata_allowlist": sorted(self.metadata_allowlist),
                "limits": {
                    "max_bytes": self.limits.max_bytes,
                    "max_pixels": self.limits.max_pixels,
                    "max_audio_seconds": self.limits.max_audio_seconds,
                    "max_video_seconds": self.limits.max_video_seconds,
                    "max_frames": self.limits.max_frames,
                },
                "max_metadata_value_chars": self.max_metadata_value_chars,
            }
        )


@dataclass(frozen=True, slots=True)
class IngestReceipt:
    asset_digest: str
    source_digest: str
    policy_digest: str
    metadata_digest: str
    pipeline_id: str
    media_type: str
    format: str

    def __post_init__(self) -> None:
        for name in ("asset_digest", "source_digest", "policy_digest", "metadata_digest"):
            object.__setattr__(self, name, _digest_text(getattr(self, name), name))
        object.__setattr__(self, "pipeline_id", _token(self.pipeline_id, "pipeline_id"))
        object.__setattr__(self, "media_type", _token(self.media_type, "media_type"))
        object.__setattr__(self, "format", _token(self.format, "format"))


class MultimodalIngestionCore:
    """Fail-closed admission registry in front of all modality decoders."""

    def __init__(
        self,
        policy: IngestionPolicy,
        bindings: Sequence[PipelineBinding],
    ) -> None:
        self.policy = policy
        by_media: dict[str, PipelineBinding] = {}
        for binding in bindings:
            if binding.media_type in by_media:
                raise IngestionError(
                    f"duplicate pipeline binding for {binding.media_type!r}"
                )
            by_media[binding.media_type] = binding
        missing = policy.allowed_media_types.difference(by_media)
        if missing:
            raise IngestionError(
                "missing pipeline bindings for: " + ", ".join(sorted(missing))
            )
        self._bindings = by_media
        self._assets_by_source: dict[str, MultimodalAsset] = {}
        self._receipts_by_source: dict[str, IngestReceipt] = {}
        self._transforms_by_output: dict[str, MediaTransform] = {}
        self._content_modalities: dict[str, str] = {}

    def _validate_probe(self, payload: bytes, probe: MediaProbe) -> PipelineBinding:
        if not isinstance(payload, (bytes, bytearray)):
            raise TypeError("payload must be bytes")
        actual_size = len(payload)
        if probe.byte_size != actual_size:
            raise IngestionError("declared byte_size does not match source bytes")
        if actual_size > self.policy.limits.max_bytes:
            raise IngestionError("asset exceeds configured byte limit")
        if probe.media_type not in self.policy.allowed_media_types:
            raise IngestionError("media_type is not allowed")
        binding = self._bindings[probe.media_type]
        if probe.format not in binding.accepted_formats:
            raise IngestionError("format is not accepted by the modality pipeline")

        pixels = probe.pixels
        if pixels is not None and pixels > self.policy.limits.max_pixels:
            raise IngestionError("asset exceeds configured pixel limit")
        if probe.media_type == "audio":
            if probe.duration_seconds is None:
                raise IngestionError("audio duration is required before decode")
            if probe.duration_seconds > self.policy.limits.max_audio_seconds:
                raise IngestionError("audio exceeds configured duration limit")
        if probe.media_type == "video":
            if probe.duration_seconds is None or probe.fps is None:
                raise IngestionError("video duration and fps are required before decode")
            if probe.duration_seconds > self.policy.limits.max_video_seconds:
                raise IngestionError("video exceeds configured duration limit")
            estimated_frames = probe.estimated_frames
            if estimated_frames is None or estimated_frames > self.policy.limits.max_frames:
                raise IngestionError("video exceeds configured frame budget")
        return binding

    def admit_predecode(
        self,
        payload: bytes,
        probe: MediaProbe,
        *,
        trust_label: str,
        classification: str,
        asset_id: str | None = None,
    ) -> tuple[MultimodalAsset, IngestReceipt]:
        trust = _token(trust_label, "trust_label")
        classification = _token(classification, "classification")
        if trust not in self.policy.allowed_trust_labels:
            raise IngestionError("trust label is not admitted")
        if classification not in self.policy.allowed_classifications:
            raise IngestionError("classification is not admitted")

        binding = self._validate_probe(payload, probe)
        safe_metadata = _safe_metadata(
            probe.metadata,
            allowlist=self.policy.metadata_allowlist,
            max_value_chars=self.policy.max_metadata_value_chars,
        )
        metadata = MediaMetadata(
            media_type=probe.media_type,
            format=probe.format,
            width=probe.width,
            height=probe.height,
            duration_seconds=probe.duration_seconds,
            sample_rate_hz=probe.sample_rate_hz,
            channels=probe.channels,
        )
        source_digest = digest_bytes(bytes(payload))
        stable_asset_id = (
            _token(asset_id, "asset_id") if asset_id is not None else f"MM.{source_digest[:24]}"
        )
        asset = MultimodalAsset(
            asset_id=stable_asset_id,
            media_type=probe.media_type,
            source_digest=source_digest,
            byte_size=len(payload),
            trust_label=trust,
            classification=classification,
            metadata={
                "format": probe.format,
                "media_metadata_digest": metadata.digest,
                "safe_metadata": safe_metadata,
            },
        )
        previous = self._assets_by_source.get(source_digest)
        if previous is not None and previous != asset:
            raise IngestionError("source digest already exists with different metadata")
        metadata_digest = _digest(
            {
                "media": metadata.digest,
                "safe_metadata": safe_metadata,
            }
        )
        receipt = IngestReceipt(
            asset_digest=asset.digest,
            source_digest=source_digest,
            policy_digest=self.policy.digest,
            metadata_digest=metadata_digest,
            pipeline_id=binding.pipeline_id,
            media_type=probe.media_type,
            format=probe.format,
        )
        previous_receipt = self._receipts_by_source.get(source_digest)
        if previous_receipt is not None and previous_receipt != receipt:
            raise IngestionError("source digest already exists with different admission")
        self._assets_by_source[source_digest] = asset
        self._receipts_by_source[source_digest] = receipt
        self._content_modalities[source_digest] = probe.media_type
        return asset, receipt

    def record_transform(self, transform: MediaTransform) -> None:
        source = _digest_text(transform.source_digest, "source_digest")
        output = _digest_text(transform.output_digest, "output_digest")
        if source == output:
            raise IngestionError("transform output must differ from source")
        source_modality = self._content_modalities.get(source)
        if source_modality is None:
            raise IngestionError("transform source is not admitted")
        if transform.modality != source_modality:
            raise IngestionError("transform modality does not match source modality")
        if output in self._content_modalities or output in self._transforms_by_output:
            raise IngestionError("transform output digest is already registered")
        self._transforms_by_output[output] = transform
        self._content_modalities[output] = source_modality

    def asset_for_source(self, source_digest: str) -> MultimodalAsset:
        return self._assets_by_source[_digest_text(source_digest, "source_digest")]

    def receipt_for_source(self, source_digest: str) -> IngestReceipt:
        return self._receipts_by_source[_digest_text(source_digest, "source_digest")]

    def lineage(self, output_digest: str) -> tuple[MediaTransform, ...]:
        cursor = _digest_text(output_digest, "output_digest")
        if cursor not in self._content_modalities:
            raise IngestionError("content digest is not registered")
        chain: list[MediaTransform] = []
        seen: set[str] = set()
        while cursor in self._transforms_by_output:
            if cursor in seen:
                raise IngestionError("transform lineage cycle detected")
            seen.add(cursor)
            transform = self._transforms_by_output[cursor]
            chain.append(transform)
            cursor = transform.source_digest
        if cursor not in self._assets_by_source:
            raise IngestionError("transform lineage does not terminate at an admitted source")
        chain.reverse()
        return tuple(chain)

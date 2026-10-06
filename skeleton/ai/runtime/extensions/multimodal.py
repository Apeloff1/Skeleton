"""Bounded multimodal runtime contracts for the P3 deferred frontier.

This module materializes VOL-153 through VOL-159 as provider-independent,
content-addressed contracts.  It deliberately performs validation and evidence
bookkeeping only; codecs/model backends remain replaceable adapters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
from typing import Any, Iterable, Mapping, Sequence


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _require_digest(value: str, *, field_name: str) -> str:
    text = str(value).strip().lower()
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ValueError(f"{field_name} must be a lowercase sha256 digest")
    return text


def _require_nonempty(value: str, *, field_name: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} must be non-empty")
    return text


def _require_int(value: object, *, field_name: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{field_name} must be an integer >= {minimum}")
    return value


def _require_number(
    value: object,
    *,
    field_name: str,
    minimum: float = 0.0,
    strictly_positive: bool = False,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be a finite number")
    if strictly_positive:
        if number <= minimum:
            raise ValueError(f"{field_name} must be > {minimum}")
    elif number < minimum:
        raise ValueError(f"{field_name} must be >= {minimum}")
    return number


def digest_bytes(payload: bytes) -> str:
    if not isinstance(payload, (bytes, bytearray)):
        raise TypeError("payload must be bytes")
    return hashlib.sha256(bytes(payload)).hexdigest()


@dataclass(frozen=True, slots=True)
class ResourceLimits:
    max_bytes: int = 32 * 1024 * 1024
    max_pixels: int = 64_000_000
    max_audio_seconds: float = 3_600.0
    max_video_seconds: float = 3_600.0
    max_frames: int = 36_000

    def __post_init__(self) -> None:
        object.__setattr__(self, "max_bytes", _require_int(self.max_bytes, field_name="max_bytes", minimum=1))
        object.__setattr__(self, "max_pixels", _require_int(self.max_pixels, field_name="max_pixels", minimum=1))
        object.__setattr__(self, "max_frames", _require_int(self.max_frames, field_name="max_frames", minimum=1))
        object.__setattr__(
            self,
            "max_audio_seconds",
            _require_number(
                self.max_audio_seconds,
                field_name="max_audio_seconds",
                strictly_positive=True,
            ),
        )
        object.__setattr__(
            self,
            "max_video_seconds",
            _require_number(
                self.max_video_seconds,
                field_name="max_video_seconds",
                strictly_positive=True,
            ),
        )


@dataclass(frozen=True, slots=True)
class MediaMetadata:
    media_type: str
    format: str
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None
    sample_rate_hz: int | None = None
    channels: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "media_type", _require_nonempty(self.media_type, field_name="media_type"))
        object.__setattr__(self, "format", _require_nonempty(self.format, field_name="format"))
        if (self.width is None) != (self.height is None):
            raise ValueError("width and height must be supplied together")
        if self.width is not None:
            object.__setattr__(self, "width", _require_int(self.width, field_name="width", minimum=1))
            object.__setattr__(self, "height", _require_int(self.height, field_name="height", minimum=1))
        if self.duration_seconds is not None:
            object.__setattr__(
                self,
                "duration_seconds",
                _require_number(self.duration_seconds, field_name="duration_seconds"),
            )
        if self.sample_rate_hz is not None:
            object.__setattr__(
                self,
                "sample_rate_hz",
                _require_int(self.sample_rate_hz, field_name="sample_rate_hz", minimum=1),
            )
        if self.channels is not None:
            object.__setattr__(
                self,
                "channels",
                _require_int(self.channels, field_name="channels", minimum=1),
            )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "media_type": self.media_type,
                "format": self.format,
                "width": self.width,
                "height": self.height,
                "duration_seconds": self.duration_seconds,
                "sample_rate_hz": self.sample_rate_hz,
                "channels": self.channels,
            }
        )


@dataclass(frozen=True, slots=True)
class MultimodalAsset:
    asset_id: str
    media_type: str
    source_digest: str
    byte_size: int
    trust_label: str
    classification: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "asset_id", _require_nonempty(self.asset_id, field_name="asset_id"))
        object.__setattr__(self, "media_type", _require_nonempty(self.media_type, field_name="media_type"))
        object.__setattr__(self, "source_digest", _require_digest(self.source_digest, field_name="source_digest"))
        object.__setattr__(self, "trust_label", _require_nonempty(self.trust_label, field_name="trust_label"))
        object.__setattr__(self, "classification", _require_nonempty(self.classification, field_name="classification"))
        object.__setattr__(self, "byte_size", _require_int(self.byte_size, field_name="byte_size"))
        copied = dict(self.metadata)
        _canonical(copied)
        object.__setattr__(self, "metadata", copied)

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())

    def as_dict(self) -> dict[str, object]:
        return {
            "asset_id": self.asset_id,
            "media_type": self.media_type,
            "source_digest": self.source_digest,
            "byte_size": self.byte_size,
            "trust_label": self.trust_label,
            "classification": self.classification,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class MediaTransform:
    transform_id: str
    source_digest: str
    output_digest: str
    modality: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    source_offsets: tuple[float, float] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "transform_id", _require_nonempty(self.transform_id, field_name="transform_id"))
        object.__setattr__(self, "source_digest", _require_digest(self.source_digest, field_name="source_digest"))
        object.__setattr__(self, "output_digest", _require_digest(self.output_digest, field_name="output_digest"))
        object.__setattr__(self, "modality", _require_nonempty(self.modality, field_name="modality"))
        params = dict(self.parameters)
        _canonical(params)
        object.__setattr__(self, "parameters", params)
        if self.source_offsets is not None:
            start, end = self.source_offsets
            start = _require_number(start, field_name="source_offset_start")
            end = _require_number(end, field_name="source_offset_end")
            if start > end:
                raise ValueError("source_offsets must be ordered")
            object.__setattr__(self, "source_offsets", (start, end))

    @property
    def digest(self) -> str:
        return _digest(
            {
                "transform_id": self.transform_id,
                "source_digest": self.source_digest,
                "output_digest": self.output_digest,
                "modality": self.modality,
                "parameters": dict(self.parameters),
                "source_offsets": self.source_offsets,
            }
        )


@dataclass(frozen=True, slots=True)
class ImageAsset:
    asset_digest: str
    width: int
    height: int
    format: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "asset_digest", _require_digest(self.asset_digest, field_name="asset_digest"))
        object.__setattr__(self, "format", _require_nonempty(self.format, field_name="format"))
        object.__setattr__(self, "width", _require_int(self.width, field_name="width", minimum=1))
        object.__setattr__(self, "height", _require_int(self.height, field_name="height", minimum=1))

    @property
    def pixels(self) -> int:
        return self.width * self.height


@dataclass(frozen=True, slots=True)
class ImageRegion:
    asset_digest: str
    x: int
    y: int
    width: int
    height: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "asset_digest", _require_digest(self.asset_digest, field_name="asset_digest"))
        object.__setattr__(self, "x", _require_int(self.x, field_name="x"))
        object.__setattr__(self, "y", _require_int(self.y, field_name="y"))
        object.__setattr__(self, "width", _require_int(self.width, field_name="width", minimum=1))
        object.__setattr__(self, "height", _require_int(self.height, field_name="height", minimum=1))

    def validate_within(self, image: ImageAsset) -> None:
        if image.asset_digest != self.asset_digest:
            raise ValueError("region does not reference the supplied image")
        if self.x + self.width > image.width or self.y + self.height > image.height:
            raise ValueError("region extends beyond source image")


@dataclass(frozen=True, slots=True)
class VisionResult:
    asset_digest: str
    model_id: str
    confidence: float
    regions: tuple[ImageRegion, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "asset_digest", _require_digest(self.asset_digest, field_name="asset_digest"))
        object.__setattr__(self, "model_id", _require_nonempty(self.model_id, field_name="model_id"))
        confidence = _require_number(self.confidence, field_name="confidence")
        if confidence > 1.0:
            raise ValueError("confidence must be finite in [0, 1]")
        object.__setattr__(self, "confidence", confidence)


@dataclass(frozen=True, slots=True)
class DocumentPage:
    document_digest: str
    page_number: int
    width: int
    height: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "document_digest", _require_digest(self.document_digest, field_name="document_digest"))
        object.__setattr__(self, "page_number", _require_int(self.page_number, field_name="page_number", minimum=1))
        object.__setattr__(self, "width", _require_int(self.width, field_name="width", minimum=1))
        object.__setattr__(self, "height", _require_int(self.height, field_name="height", minimum=1))


@dataclass(frozen=True, slots=True)
class OCRSpan:
    document_digest: str
    page_number: int
    text: str
    x: int
    y: int
    width: int
    height: int
    confidence: float
    source: str = "ocr"

    def __post_init__(self) -> None:
        object.__setattr__(self, "document_digest", _require_digest(self.document_digest, field_name="document_digest"))
        object.__setattr__(self, "text", _require_nonempty(self.text, field_name="text"))
        object.__setattr__(self, "source", _require_nonempty(self.source, field_name="source"))
        object.__setattr__(self, "page_number", _require_int(self.page_number, field_name="page_number", minimum=1))
        object.__setattr__(self, "x", _require_int(self.x, field_name="x"))
        object.__setattr__(self, "y", _require_int(self.y, field_name="y"))
        object.__setattr__(self, "width", _require_int(self.width, field_name="width", minimum=1))
        object.__setattr__(self, "height", _require_int(self.height, field_name="height", minimum=1))
        confidence = _require_number(self.confidence, field_name="OCR confidence")
        if confidence > 1.0:
            raise ValueError("OCR confidence must be finite in [0, 1]")
        object.__setattr__(self, "confidence", confidence)


@dataclass(frozen=True, slots=True)
class LayoutRegion:
    document_digest: str
    page_number: int
    kind: str
    span_digests: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "document_digest", _require_digest(self.document_digest, field_name="document_digest"))
        object.__setattr__(self, "kind", _require_nonempty(self.kind, field_name="kind"))
        object.__setattr__(self, "page_number", _require_int(self.page_number, field_name="page_number", minimum=1))
        spans = tuple(_require_digest(item, field_name="span_digest") for item in self.span_digests)
        if len(spans) != len(set(spans)):
            raise ValueError("layout region span digests must be unique")
        object.__setattr__(self, "span_digests", spans)


@dataclass(frozen=True, slots=True)
class AudioAsset:
    asset_digest: str
    sample_rate_hz: int
    channels: int
    duration_seconds: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "asset_digest", _require_digest(self.asset_digest, field_name="asset_digest"))
        object.__setattr__(
            self,
            "sample_rate_hz",
            _require_int(self.sample_rate_hz, field_name="sample_rate_hz", minimum=1),
        )
        object.__setattr__(self, "channels", _require_int(self.channels, field_name="channels", minimum=1))
        object.__setattr__(
            self,
            "duration_seconds",
            _require_number(self.duration_seconds, field_name="duration_seconds"),
        )


@dataclass(frozen=True, slots=True)
class AudioSegment:
    asset_digest: str
    start_seconds: float
    end_seconds: float
    source_channel: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "asset_digest", _require_digest(self.asset_digest, field_name="asset_digest"))
        start = _require_number(self.start_seconds, field_name="start_seconds")
        end = _require_number(self.end_seconds, field_name="end_seconds")
        if start >= end:
            raise ValueError("audio segment timestamps are invalid")
        object.__setattr__(self, "start_seconds", start)
        object.__setattr__(self, "end_seconds", end)
        object.__setattr__(
            self,
            "source_channel",
            _require_int(self.source_channel, field_name="source_channel"),
        )

    def validate_within(self, asset: AudioAsset) -> None:
        if self.asset_digest != asset.asset_digest:
            raise ValueError("segment does not reference the supplied audio asset")
        if self.end_seconds > asset.duration_seconds:
            raise ValueError("segment exceeds source audio duration")


@dataclass(frozen=True, slots=True)
class AudioResult:
    asset_digest: str
    model_id: str
    task: str
    confidence: float
    segments: tuple[AudioSegment, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "asset_digest", _require_digest(self.asset_digest, field_name="asset_digest"))
        object.__setattr__(self, "model_id", _require_nonempty(self.model_id, field_name="model_id"))
        object.__setattr__(self, "task", _require_nonempty(self.task, field_name="task"))
        confidence = _require_number(self.confidence, field_name="confidence")
        if confidence > 1.0:
            raise ValueError("confidence must be finite in [0, 1]")
        object.__setattr__(self, "confidence", confidence)


@dataclass(frozen=True, slots=True)
class TranscriptSegment:
    session_id: str
    sequence: int
    text: str
    start_seconds: float
    end_seconds: float
    final: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "session_id", _require_nonempty(self.session_id, field_name="session_id"))
        object.__setattr__(self, "text", _require_nonempty(self.text, field_name="text"))
        object.__setattr__(self, "sequence", _require_int(self.sequence, field_name="sequence"))
        if not isinstance(self.final, bool):
            raise ValueError("final must be boolean")
        start = _require_number(self.start_seconds, field_name="start_seconds")
        end = _require_number(self.end_seconds, field_name="end_seconds")
        if start > end:
            raise ValueError("transcript timestamps are invalid")
        object.__setattr__(self, "start_seconds", start)
        object.__setattr__(self, "end_seconds", end)


@dataclass(frozen=True, slots=True)
class SpeechFrame:
    session_id: str
    sequence: int
    timestamp_seconds: float
    payload_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "session_id", _require_nonempty(self.session_id, field_name="session_id"))
        object.__setattr__(self, "payload_digest", _require_digest(self.payload_digest, field_name="payload_digest"))
        object.__setattr__(self, "sequence", _require_int(self.sequence, field_name="sequence"))
        object.__setattr__(
            self,
            "timestamp_seconds",
            _require_number(self.timestamp_seconds, field_name="timestamp_seconds"),
        )


class SpeechSession:
    """Small explicit state machine for reconnect, cancellation and barge-in."""

    _ALLOWED = {
        "new": {"active", "cancelled"},
        "active": {"reconnecting", "barge_in", "closed", "cancelled"},
        "reconnecting": {"active", "cancelled"},
        "barge_in": {"active", "closed", "cancelled"},
        "closed": set(),
        "cancelled": set(),
    }

    def __init__(self, session_id: str, *, max_segments: int = 4096) -> None:
        self.session_id = _require_nonempty(session_id, field_name="session_id")
        self.max_segments = _require_int(max_segments, field_name="max_segments", minimum=1)
        self.state = "new"
        self._segments: list[TranscriptSegment] = []

    @property
    def segments(self) -> tuple[TranscriptSegment, ...]:
        return tuple(self._segments)

    @property
    def authoritative_text(self) -> str:
        return " ".join(item.text for item in self._segments if item.final)

    def transition(self, state: str) -> None:
        state = _require_nonempty(state, field_name="state")
        if state not in self._ALLOWED.get(self.state, set()):
            raise ValueError(f"invalid speech transition {self.state!r} -> {state!r}")
        self.state = state

    def append(self, segment: TranscriptSegment) -> None:
        if self.state != "active":
            raise ValueError("transcripts may only be appended while active")
        if segment.session_id != self.session_id:
            raise ValueError("segment belongs to another speech session")
        if len(self._segments) >= self.max_segments:
            raise BufferError("speech transcript backpressure limit reached")
        expected = len(self._segments)
        if segment.sequence != expected:
            raise ValueError(f"segment sequence must be {expected}")
        if self._segments and segment.start_seconds < self._segments[-1].start_seconds:
            raise ValueError("transcript timestamps must be monotonic")
        self._segments.append(segment)

    def replace_provisional(self, segment: TranscriptSegment) -> None:
        if self.state != "active":
            raise ValueError("transcripts may only be replaced while active")
        if not self._segments or self._segments[-1].final:
            raise ValueError("there is no provisional transcript to replace")
        previous = self._segments[-1]
        if segment.final or segment.sequence != previous.sequence or segment.session_id != self.session_id:
            raise ValueError("replacement must target the same provisional segment")
        self._segments[-1] = segment

    def finalize_provisional(self, segment: TranscriptSegment) -> None:
        """Atomically promote the current provisional segment to authority."""

        if self.state != "active":
            raise ValueError("transcripts may only be finalized while active")
        if not self._segments or self._segments[-1].final:
            raise ValueError("there is no provisional transcript to finalize")
        previous = self._segments[-1]
        if (
            not segment.final
            or segment.sequence != previous.sequence
            or segment.session_id != self.session_id
        ):
            raise ValueError("finalization must target the same provisional segment")
        if segment.start_seconds < previous.start_seconds:
            raise ValueError("final transcript cannot move before provisional start")
        self._segments[-1] = segment


@dataclass(frozen=True, slots=True)
class VideoAsset:
    asset_digest: str
    width: int
    height: int
    duration_seconds: float
    fps: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "asset_digest", _require_digest(self.asset_digest, field_name="asset_digest"))
        object.__setattr__(self, "width", _require_int(self.width, field_name="width", minimum=1))
        object.__setattr__(self, "height", _require_int(self.height, field_name="height", minimum=1))
        object.__setattr__(
            self,
            "duration_seconds",
            _require_number(self.duration_seconds, field_name="duration_seconds"),
        )
        object.__setattr__(
            self,
            "fps",
            _require_number(self.fps, field_name="fps", strictly_positive=True),
        )


@dataclass(frozen=True, slots=True)
class VideoSegment:
    asset_digest: str
    start_seconds: float
    end_seconds: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "asset_digest", _require_digest(self.asset_digest, field_name="asset_digest"))
        start = _require_number(self.start_seconds, field_name="start_seconds")
        end = _require_number(self.end_seconds, field_name="end_seconds")
        if start >= end:
            raise ValueError("video segment timestamps are invalid")
        object.__setattr__(self, "start_seconds", start)
        object.__setattr__(self, "end_seconds", end)


@dataclass(frozen=True, slots=True)
class FrameSample:
    asset_digest: str
    timestamp_seconds: float
    frame_digest: str
    source_frame_index: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "asset_digest", _require_digest(self.asset_digest, field_name="asset_digest"))
        object.__setattr__(self, "frame_digest", _require_digest(self.frame_digest, field_name="frame_digest"))
        object.__setattr__(
            self,
            "source_frame_index",
            _require_int(self.source_frame_index, field_name="source_frame_index"),
        )
        object.__setattr__(
            self,
            "timestamp_seconds",
            _require_number(self.timestamp_seconds, field_name="timestamp_seconds"),
        )


def detect_document_text_conflict(
    ocr_text: str,
    text_layer: str,
    *,
    normalize_whitespace: bool = True,
) -> bool:
    """Return True when independent OCR and embedded text materially disagree."""

    left = _require_nonempty(ocr_text, field_name="ocr_text")
    right = _require_nonempty(text_layer, field_name="text_layer")
    if normalize_whitespace:
        left = " ".join(left.split())
        right = " ".join(right.split())
    return left != right


def sample_video_timestamps(
    asset: VideoAsset,
    *,
    interval_seconds: float,
    max_samples: int,
) -> tuple[float, ...]:
    """Build a deterministic bounded temporal sampling plan before decoding frames."""

    interval_seconds = _require_number(
        interval_seconds,
        field_name="interval_seconds",
        strictly_positive=True,
    )
    max_samples = _require_int(max_samples, field_name="max_samples", minimum=1)
    if asset.duration_seconds == 0:
        return (0.0,)
    timestamps: list[float] = []
    cursor = 0.0
    while cursor < asset.duration_seconds and len(timestamps) < max_samples:
        timestamps.append(round(cursor, 9))
        cursor += interval_seconds
    if cursor < asset.duration_seconds:
        raise ValueError("sampling plan exceeds max_samples budget")
    return tuple(timestamps)


@dataclass(frozen=True, slots=True)
class MultimodalQuery:
    text: str
    modalities: tuple[str, ...]
    tenant_id: str
    allowed_classifications: frozenset[str]
    allowed_trust_labels: frozenset[str]
    as_of_epoch: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "text", _require_nonempty(self.text, field_name="text"))
        object.__setattr__(self, "tenant_id", _require_nonempty(self.tenant_id, field_name="tenant_id"))
        modalities = tuple(_require_nonempty(item, field_name="modality") for item in self.modalities)
        if not modalities:
            raise ValueError("at least one modality is required")
        if len(modalities) != len(set(modalities)):
            raise ValueError("modalities must be unique")
        object.__setattr__(self, "modalities", modalities)
        classifications = frozenset(
            _require_nonempty(item, field_name="allowed_classification")
            for item in self.allowed_classifications
        )
        trust_labels = frozenset(
            _require_nonempty(item, field_name="allowed_trust_label")
            for item in self.allowed_trust_labels
        )
        if not classifications or not trust_labels:
            raise ValueError("classification and trust filters must be explicit")
        object.__setattr__(self, "allowed_classifications", classifications)
        object.__setattr__(self, "allowed_trust_labels", trust_labels)
        if self.as_of_epoch is not None:
            object.__setattr__(
                self,
                "as_of_epoch",
                _require_int(self.as_of_epoch, field_name="as_of_epoch"),
            )


@dataclass(frozen=True, slots=True)
class MultimodalHit:
    asset_digest: str
    modality: str
    tenant_id: str
    classification: str
    trust_label: str
    score: float
    indexed_epoch: int
    evidence_digest: str

    def __post_init__(self) -> None:
        for name in ("asset_digest", "evidence_digest"):
            object.__setattr__(self, name, _require_digest(getattr(self, name), field_name=name))
        for name in ("modality", "tenant_id", "classification", "trust_label"):
            object.__setattr__(self, name, _require_nonempty(getattr(self, name), field_name=name))
        object.__setattr__(self, "score", _require_number(self.score, field_name="score"))
        object.__setattr__(
            self,
            "indexed_epoch",
            _require_int(self.indexed_epoch, field_name="indexed_epoch"),
        )


@dataclass(frozen=True, slots=True)
class CrossModalEvidence:
    query_digest: str
    hits: tuple[MultimodalHit, ...]
    fusion_policy: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "query_digest", _require_digest(self.query_digest, field_name="query_digest"))
        object.__setattr__(self, "fusion_policy", _require_nonempty(self.fusion_policy, field_name="fusion_policy"))

    @property
    def digest(self) -> str:
        return _digest(
            {
                "query_digest": self.query_digest,
                "fusion_policy": self.fusion_policy,
                "hits": [
                    {
                        "asset_digest": h.asset_digest,
                        "modality": h.modality,
                        "tenant_id": h.tenant_id,
                        "classification": h.classification,
                        "trust_label": h.trust_label,
                        "score": h.score,
                        "indexed_epoch": h.indexed_epoch,
                        "evidence_digest": h.evidence_digest,
                    }
                    for h in self.hits
                ],
            }
        )


class MultimodalRegistry:
    """In-memory reference registry with pre-ranking trust/tenant filtering."""

    def __init__(self, *, limits: ResourceLimits | None = None) -> None:
        self.limits = limits or ResourceLimits()
        self._assets: dict[str, MultimodalAsset] = {}
        self._transforms: dict[str, MediaTransform] = {}
        self._transform_outputs: dict[str, str] = {}
        self._hits: list[MultimodalHit] = []
        self._hit_identities: dict[tuple[str, str], MultimodalHit] = {}

    def register_asset(self, asset: MultimodalAsset) -> str:
        if asset.byte_size > self.limits.max_bytes:
            raise ValueError("asset exceeds configured byte limit")
        existing = self._assets.get(asset.digest)
        if existing is not None and existing != asset:
            raise ValueError("content identity collision")
        self._assets[asset.digest] = asset
        return asset.digest

    def register_image(self, image: ImageAsset) -> None:
        if image.pixels > self.limits.max_pixels:
            raise ValueError("image exceeds configured pixel limit")

    def register_audio(self, audio: AudioAsset) -> None:
        if audio.duration_seconds > self.limits.max_audio_seconds:
            raise ValueError("audio exceeds configured duration limit")

    def register_video(self, video: VideoAsset) -> None:
        if video.duration_seconds > self.limits.max_video_seconds:
            raise ValueError("video exceeds configured duration limit")
        estimated_frames = math.ceil(video.duration_seconds * video.fps)
        if estimated_frames > self.limits.max_frames:
            raise ValueError("video exceeds configured frame budget")

    def register_transform(self, transform: MediaTransform) -> str:
        if transform.source_digest == transform.output_digest:
            raise ValueError("transform must produce distinct output identity")
        existing = self._transforms.get(transform.digest)
        if existing is not None and existing != transform:
            raise ValueError("transform identity collision")
        bound = self._transform_outputs.get(transform.output_digest)
        if bound is not None and bound != transform.digest:
            raise ValueError("transform output is already bound to different lineage")
        self._transforms[transform.digest] = transform
        self._transform_outputs[transform.output_digest] = transform.digest
        return transform.digest

    def index(self, hit: MultimodalHit) -> None:
        identity = (hit.asset_digest, hit.evidence_digest)
        existing = self._hit_identities.get(identity)
        if existing is not None:
            if existing != hit:
                raise ValueError("evidence identity is already bound to different retrieval data")
            return
        self._hit_identities[identity] = hit
        self._hits.append(hit)

    def retrieve(self, query: MultimodalQuery, *, limit: int = 20) -> CrossModalEvidence:
        limit = _require_int(limit, field_name="limit", minimum=1)
        permitted = [
            hit
            for hit in self._hits
            if hit.tenant_id == query.tenant_id
            and hit.modality in query.modalities
            and hit.classification in query.allowed_classifications
            and hit.trust_label in query.allowed_trust_labels
            and (query.as_of_epoch is None or hit.indexed_epoch <= query.as_of_epoch)
        ]
        permitted.sort(key=lambda item: (-item.score, item.asset_digest, item.evidence_digest))
        query_digest = _digest(
            {
                "text": query.text,
                "modalities": query.modalities,
                "tenant_id": query.tenant_id,
                "allowed_classifications": sorted(query.allowed_classifications),
                "allowed_trust_labels": sorted(query.allowed_trust_labels),
                "as_of_epoch": query.as_of_epoch,
            }
        )
        return CrossModalEvidence(
            query_digest=query_digest,
            hits=tuple(permitted[:limit]),
            fusion_policy="filter-before-rank/v1",
        )

    def asset(self, digest: str) -> MultimodalAsset:
        return self._assets[_require_digest(digest, field_name="digest")]

    def lineage(self, output_digest: str) -> tuple[MediaTransform, ...]:
        wanted = _require_digest(output_digest, field_name="output_digest")
        chain: list[MediaTransform] = []
        seen: set[str] = set()
        while True:
            matches = [item for item in self._transforms.values() if item.output_digest == wanted]
            if not matches:
                return tuple(reversed(chain))
            if len(matches) != 1:
                raise ValueError("ambiguous transform lineage")
            item = matches[0]
            if item.digest in seen:
                raise ValueError("transform lineage cycle detected")
            seen.add(item.digest)
            chain.append(item)
            wanted = item.source_digest


def fuse_scores(groups: Iterable[Sequence[MultimodalHit]]) -> tuple[MultimodalHit, ...]:
    """Deterministically fuse pre-filtered modality result groups.

    The reference policy does not normalize away provenance. Duplicate evidence
    is retained once at the maximum score and the ordering is deterministic.
    """

    best: dict[tuple[str, str], MultimodalHit] = {}
    for group in groups:
        for hit in group:
            key = (hit.asset_digest, hit.evidence_digest)
            previous = best.get(key)
            if previous is None or hit.score > previous.score:
                best[key] = hit
    return tuple(sorted(best.values(), key=lambda item: (-item.score, item.asset_digest, item.evidence_digest)))

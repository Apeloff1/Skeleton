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
        if self.max_bytes <= 0 or self.max_pixels <= 0 or self.max_frames <= 0:
            raise ValueError("resource limits must be positive")
        if self.max_audio_seconds <= 0 or self.max_video_seconds <= 0:
            raise ValueError("duration limits must be positive")


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
        if self.byte_size < 0:
            raise ValueError("byte_size must be non-negative")
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
            if not (math.isfinite(start) and math.isfinite(end) and 0 <= start <= end):
                raise ValueError("source_offsets must be finite ordered non-negative offsets")

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
        if self.width <= 0 or self.height <= 0:
            raise ValueError("image dimensions must be positive")

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
        if min(self.x, self.y) < 0 or self.width <= 0 or self.height <= 0:
            raise ValueError("invalid image region geometry")

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
        if not math.isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be finite in [0, 1]")


@dataclass(frozen=True, slots=True)
class DocumentPage:
    document_digest: str
    page_number: int
    width: int
    height: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "document_digest", _require_digest(self.document_digest, field_name="document_digest"))
        if self.page_number <= 0 or self.width <= 0 or self.height <= 0:
            raise ValueError("document page geometry must be positive")


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
        if self.page_number <= 0 or min(self.x, self.y) < 0 or self.width <= 0 or self.height <= 0:
            raise ValueError("invalid OCR geometry")
        if not math.isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0:
            raise ValueError("OCR confidence must be finite in [0, 1]")


@dataclass(frozen=True, slots=True)
class LayoutRegion:
    document_digest: str
    page_number: int
    kind: str
    span_digests: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "document_digest", _require_digest(self.document_digest, field_name="document_digest"))
        object.__setattr__(self, "kind", _require_nonempty(self.kind, field_name="kind"))
        if self.page_number <= 0:
            raise ValueError("page_number must be positive")
        for item in self.span_digests:
            _require_digest(item, field_name="span_digest")


@dataclass(frozen=True, slots=True)
class AudioAsset:
    asset_digest: str
    sample_rate_hz: int
    channels: int
    duration_seconds: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "asset_digest", _require_digest(self.asset_digest, field_name="asset_digest"))
        if self.sample_rate_hz <= 0 or self.channels <= 0:
            raise ValueError("audio rate/channels must be positive")
        if not math.isfinite(self.duration_seconds) or self.duration_seconds < 0:
            raise ValueError("audio duration must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class AudioSegment:
    asset_digest: str
    start_seconds: float
    end_seconds: float
    source_channel: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "asset_digest", _require_digest(self.asset_digest, field_name="asset_digest"))
        if not (
            math.isfinite(self.start_seconds)
            and math.isfinite(self.end_seconds)
            and 0 <= self.start_seconds < self.end_seconds
        ):
            raise ValueError("audio segment timestamps are invalid")
        if self.source_channel < 0:
            raise ValueError("source_channel must be non-negative")

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
        if not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be finite in [0, 1]")


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
        if self.sequence < 0:
            raise ValueError("sequence must be non-negative")
        if not (
            math.isfinite(self.start_seconds)
            and math.isfinite(self.end_seconds)
            and 0 <= self.start_seconds <= self.end_seconds
        ):
            raise ValueError("transcript timestamps are invalid")


@dataclass(frozen=True, slots=True)
class SpeechFrame:
    session_id: str
    sequence: int
    timestamp_seconds: float
    payload_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "session_id", _require_nonempty(self.session_id, field_name="session_id"))
        object.__setattr__(self, "payload_digest", _require_digest(self.payload_digest, field_name="payload_digest"))
        if self.sequence < 0 or not math.isfinite(self.timestamp_seconds) or self.timestamp_seconds < 0:
            raise ValueError("invalid speech frame sequence/timestamp")


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

    def __init__(self, session_id: str) -> None:
        self.session_id = _require_nonempty(session_id, field_name="session_id")
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
        expected = len(self._segments)
        if segment.sequence != expected:
            raise ValueError(f"segment sequence must be {expected}")
        self._segments.append(segment)

    def replace_provisional(self, segment: TranscriptSegment) -> None:
        if not self._segments or self._segments[-1].final:
            raise ValueError("there is no provisional transcript to replace")
        previous = self._segments[-1]
        if segment.final or segment.sequence != previous.sequence or segment.session_id != self.session_id:
            raise ValueError("replacement must target the same provisional segment")
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
        if self.width <= 0 or self.height <= 0:
            raise ValueError("video dimensions must be positive")
        if not math.isfinite(self.duration_seconds) or self.duration_seconds < 0:
            raise ValueError("video duration must be finite and non-negative")
        if not math.isfinite(self.fps) or self.fps <= 0:
            raise ValueError("fps must be finite and positive")


@dataclass(frozen=True, slots=True)
class VideoSegment:
    asset_digest: str
    start_seconds: float
    end_seconds: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "asset_digest", _require_digest(self.asset_digest, field_name="asset_digest"))
        if not (
            math.isfinite(self.start_seconds)
            and math.isfinite(self.end_seconds)
            and 0 <= self.start_seconds < self.end_seconds
        ):
            raise ValueError("video segment timestamps are invalid")


@dataclass(frozen=True, slots=True)
class FrameSample:
    asset_digest: str
    timestamp_seconds: float
    frame_digest: str
    source_frame_index: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "asset_digest", _require_digest(self.asset_digest, field_name="asset_digest"))
        object.__setattr__(self, "frame_digest", _require_digest(self.frame_digest, field_name="frame_digest"))
        if self.source_frame_index < 0:
            raise ValueError("source_frame_index must be non-negative")
        if not math.isfinite(self.timestamp_seconds) or self.timestamp_seconds < 0:
            raise ValueError("frame timestamp must be finite and non-negative")


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
        if not self.modalities:
            raise ValueError("at least one modality is required")
        if self.as_of_epoch is not None and self.as_of_epoch < 0:
            raise ValueError("as_of_epoch must be non-negative")


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
        if not math.isfinite(self.score):
            raise ValueError("score must be finite")
        if self.indexed_epoch < 0:
            raise ValueError("indexed_epoch must be non-negative")


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
        self._hits: list[MultimodalHit] = []

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
        self._transforms[transform.digest] = transform
        return transform.digest

    def index(self, hit: MultimodalHit) -> None:
        self._hits.append(hit)

    def retrieve(self, query: MultimodalQuery, *, limit: int = 20) -> CrossModalEvidence:
        if limit <= 0:
            raise ValueError("limit must be positive")
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

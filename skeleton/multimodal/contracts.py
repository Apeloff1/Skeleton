"""Typed multimodal contracts for VOL-020.

All media-derived content is evidence. No image text, document text, transcript,
caption, OCR result, embedded metadata, subtitle, EXIF field, ID3 tag, or video
annotation may acquire instruction/policy authority merely because it was
extracted from a media artifact.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
from typing import Any, Mapping


MULTIMODAL_SCHEMA = "skeleton.multimodal.v1"


class MultimodalError(ValueError):
    """Multimodal identity, provenance, classification, or trust is invalid."""


class Modality(str, Enum):
    DOCUMENT = "document"
    IMAGE = "image"
    AUDIO = "audio"
    SPEECH = "speech"
    VIDEO = "video"


class SegmentKind(str, Enum):
    TEXT = "text"
    IMAGE_REGION = "image_region"
    AUDIO_SPAN = "audio_span"
    SPEECH_SPAN = "speech_span"
    VIDEO_FRAME = "video_frame"
    VIDEO_SPAN = "video_span"
    DOCUMENT_PAGE = "document_page"
    DOCUMENT_BLOCK = "document_block"


class TrustClass(str, Enum):
    """Trust is evidence-oriented, deliberately separate from data class."""

    UNTRUSTED_EVIDENCE = "untrusted_evidence"
    SANITIZED_EVIDENCE = "sanitized_evidence"
    VERIFIED_DERIVATION = "verified_derivation"


class CrossModalRelation(str, Enum):
    DERIVED_FROM = "derived_from"
    ALIGNED_WITH = "aligned_with"
    TRANSCRIPT_OF = "transcript_of"
    CAPTION_OF = "caption_of"
    FRAME_OF = "frame_of"
    OCR_OF = "ocr_of"
    SUMMARY_OF = "summary_of"


def _token(
    value: object,
    field: str,
    *,
    maximum: int = 1024,
    lower: bool = False,
) -> str:
    if not isinstance(value, str):
        raise MultimodalError(f"{field} must be a string")
    stripped = value.strip()
    normalized = stripped.lower() if lower else stripped
    expected = value.lower() if lower else value
    if not normalized or normalized != expected or len(normalized) > maximum:
        raise MultimodalError(f"{field} must be canonical non-empty text")
    return normalized


def _sha256(value: object, field: str) -> str:
    token = _token(value, field, maximum=64, lower=True)
    if len(token) != 64 or any(ch not in "0123456789abcdef" for ch in token):
        raise MultimodalError(f"{field} must be lowercase SHA-256")
    return token


def _finite(
    value: object,
    field: str,
    *,
    non_negative: bool = False,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MultimodalError(f"{field} must be finite numeric")
    result = float(value)
    if not math.isfinite(result):
        raise MultimodalError(f"{field} must be finite numeric")
    if non_negative and result < 0:
        raise MultimodalError(f"{field} must be non-negative")
    return result


def _unit(value: object, field: str) -> float:
    result = _finite(value, field)
    if not 0.0 <= result <= 1.0:
        raise MultimodalError(f"{field} must be within [0, 1]")
    return result


def _non_negative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise MultimodalError(f"{field} must be non-negative integer")
    return value


def _canonical_bytes(value: object, field: str = "payload") -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise MultimodalError(f"{field} must be canonical JSON") from exc


def canonical_digest(value: object, field: str = "payload") -> str:
    return hashlib.sha256(_canonical_bytes(value, field)).hexdigest()


def _canonical_mapping(
    value: Mapping[str, Any],
    field: str,
) -> tuple[tuple[str, Any], ...]:
    if not isinstance(value, Mapping):
        raise MultimodalError(f"{field} must be a mapping")
    normalized: dict[str, Any] = {}
    for raw_key, raw_value in value.items():
        key = _token(str(raw_key), f"{field}.key", maximum=256)
        if key in normalized:
            raise MultimodalError(f"{field} contains duplicate canonical key")
        _canonical_bytes(raw_value, f"{field}.{key}")
        normalized[key] = raw_value
    return tuple((key, normalized[key]) for key in sorted(normalized))


def _mapping_payload(
    value: tuple[tuple[str, Any], ...],
) -> dict[str, Any]:
    return {key: item for key, item in value}


def _enum(value: object, enum_type: type[Enum], field: str):
    try:
        return enum_type(value)
    except (ValueError, TypeError) as exc:
        raise MultimodalError(f"invalid {field}") from exc


@dataclass(frozen=True, slots=True)
class MediaProvenance:
    """Stable origin/transformation chain for one artifact."""

    root_source_ref: str
    source_ref: str
    source_sha256: str
    transformation: str
    extractor_id: str
    parent_artifact_id: str | None = None
    parent_artifact_digest: str | None = None
    observed_at: float = 0.0

    def __post_init__(self) -> None:
        for field in ("root_source_ref", "source_ref"):
            object.__setattr__(
                self,
                field,
                _token(getattr(self, field), field, maximum=4096),
            )
        object.__setattr__(
            self,
            "source_sha256",
            _sha256(self.source_sha256, "source_sha256"),
        )
        object.__setattr__(
            self,
            "transformation",
            _token(self.transformation, "transformation", maximum=256),
        )
        object.__setattr__(
            self,
            "extractor_id",
            _token(self.extractor_id, "extractor_id", maximum=256),
        )
        if (self.parent_artifact_id is None) != (
            self.parent_artifact_digest is None
        ):
            raise MultimodalError(
                "parent artifact id and digest must be present together"
            )
        if self.parent_artifact_id is not None:
            object.__setattr__(
                self,
                "parent_artifact_id",
                _token(
                    self.parent_artifact_id,
                    "parent_artifact_id",
                    maximum=256,
                ),
            )
            object.__setattr__(
                self,
                "parent_artifact_digest",
                _sha256(
                    self.parent_artifact_digest,
                    "parent_artifact_digest",
                ),
            )
        object.__setattr__(
            self,
            "observed_at",
            _finite(self.observed_at, "observed_at", non_negative=True),
        )

    @property
    def derived(self) -> bool:
        return self.parent_artifact_id is not None

    def payload(self) -> dict[str, object]:
        return {
            "schema": MULTIMODAL_SCHEMA,
            "kind": "media-provenance",
            "root_source_ref": self.root_source_ref,
            "source_ref": self.source_ref,
            "source_sha256": self.source_sha256,
            "transformation": self.transformation,
            "extractor_id": self.extractor_id,
            "parent_artifact_id": self.parent_artifact_id,
            "parent_artifact_digest": self.parent_artifact_digest,
            "observed_at": self.observed_at,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class MediaArtifact:
    """Typed media artifact identity without embedding unbounded bytes."""

    artifact_id: str
    modality: Modality
    mime_type: str
    size_bytes: int
    sha256: str
    data_class: str
    provenance: MediaProvenance
    metadata: tuple[tuple[str, Any], ...] = ()
    metadata_trust: TrustClass = TrustClass.SANITIZED_EVIDENCE

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "artifact_id",
            _token(self.artifact_id, "artifact_id", maximum=256),
        )
        object.__setattr__(
            self,
            "modality",
            _enum(self.modality, Modality, "modality"),
        )
        mime = _token(self.mime_type, "mime_type", maximum=256, lower=True)
        if "/" not in mime or mime.startswith("/") or mime.endswith("/"):
            raise MultimodalError("mime_type must be type/subtype")
        object.__setattr__(self, "mime_type", mime)
        object.__setattr__(
            self,
            "size_bytes",
            _non_negative_int(self.size_bytes, "size_bytes"),
        )
        object.__setattr__(self, "sha256", _sha256(self.sha256, "sha256"))
        object.__setattr__(
            self,
            "data_class",
            _token(self.data_class, "data_class", maximum=128, lower=True),
        )
        if not isinstance(self.provenance, MediaProvenance):
            raise MultimodalError("provenance must be MediaProvenance")
        if self.provenance.source_sha256 != self.sha256:
            raise MultimodalError(
                "provenance source digest must equal artifact byte digest"
            )
        try:
            trust = TrustClass(self.metadata_trust)
        except ValueError as exc:
            raise MultimodalError("invalid metadata_trust") from exc
        if trust is TrustClass.VERIFIED_DERIVATION:
            raise MultimodalError(
                "artifact metadata cannot acquire verified instruction authority"
            )
        object.__setattr__(self, "metadata_trust", trust)
        if not isinstance(self.metadata, tuple):
            raise MultimodalError("metadata must be canonical tuple pairs")
        metadata = _canonical_mapping(dict(self.metadata), "metadata")
        if metadata != self.metadata:
            raise MultimodalError("metadata must be sorted canonical pairs")
        if len(metadata) > 256:
            raise MultimodalError("metadata exceeds field count limit")

    @classmethod
    def from_metadata(
        cls,
        *,
        artifact_id: str,
        modality: Modality,
        mime_type: str,
        size_bytes: int,
        sha256: str,
        data_class: str,
        provenance: MediaProvenance,
        metadata: Mapping[str, Any],
        metadata_trust: TrustClass = TrustClass.SANITIZED_EVIDENCE,
    ) -> "MediaArtifact":
        return cls(
            artifact_id=artifact_id,
            modality=modality,
            mime_type=mime_type,
            size_bytes=size_bytes,
            sha256=sha256,
            data_class=data_class,
            provenance=provenance,
            metadata=_canonical_mapping(metadata, "metadata"),
            metadata_trust=metadata_trust,
        )

    @property
    def instruction_authority(self) -> bool:
        return False

    def payload(self) -> dict[str, object]:
        return {
            "schema": MULTIMODAL_SCHEMA,
            "kind": "media-artifact",
            "artifact_id": self.artifact_id,
            "modality": self.modality.value,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "data_class": self.data_class,
            "provenance_digest": self.provenance.digest,
            "metadata": _mapping_payload(self.metadata),
            "metadata_trust": self.metadata_trust.value,
            "instruction_authority": False,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class SegmentLocator:
    """Modality-neutral bounded location inside one media artifact."""

    page: int | None = None
    start_ms: int | None = None
    end_ms: int | None = None
    frame_index: int | None = None
    x: float | None = None
    y: float | None = None
    width: float | None = None
    height: float | None = None

    def __post_init__(self) -> None:
        if self.page is not None:
            object.__setattr__(self, "page", _non_negative_int(self.page, "page"))
        if (self.start_ms is None) != (self.end_ms is None):
            raise MultimodalError("start_ms and end_ms must be paired")
        if self.start_ms is not None:
            start = _non_negative_int(self.start_ms, "start_ms")
            end = _non_negative_int(self.end_ms, "end_ms")
            if end < start:
                raise MultimodalError("end_ms precedes start_ms")
            object.__setattr__(self, "start_ms", start)
            object.__setattr__(self, "end_ms", end)
        if self.frame_index is not None:
            object.__setattr__(
                self,
                "frame_index",
                _non_negative_int(self.frame_index, "frame_index"),
            )
        box_values = (self.x, self.y, self.width, self.height)
        present = tuple(value is not None for value in box_values)
        if any(present) and not all(present):
            raise MultimodalError(
                "x/y/width/height must be provided together"
            )
        if all(present):
            x = _unit(self.x, "x")
            y = _unit(self.y, "y")
            width = _unit(self.width, "width")
            height = _unit(self.height, "height")
            if width <= 0 or height <= 0:
                raise MultimodalError("width and height must be positive")
            if x + width > 1.0 + 1e-12 or y + height > 1.0 + 1e-12:
                raise MultimodalError(
                    "normalized media box exceeds artifact bounds"
                )
            object.__setattr__(self, "x", x)
            object.__setattr__(self, "y", y)
            object.__setattr__(self, "width", width)
            object.__setattr__(self, "height", height)

    def payload(self) -> dict[str, object]:
        return {
            "page": self.page,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "frame_index": self.frame_index,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class ModalitySegment:
    """One bounded extracted/derived unit from a media artifact."""

    segment_id: str
    artifact_id: str
    artifact_digest: str
    root_source_ref: str
    modality: Modality
    kind: SegmentKind
    sequence: int
    content_digest: str
    locator: SegmentLocator
    data_class: str
    trust_class: TrustClass
    sanitized_text: str | None = None
    findings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field in ("segment_id", "artifact_id"):
            object.__setattr__(
                self,
                field,
                _token(getattr(self, field), field, maximum=256),
            )
        object.__setattr__(
            self,
            "artifact_digest",
            _sha256(self.artifact_digest, "artifact_digest"),
        )
        object.__setattr__(
            self,
            "root_source_ref",
            _token(self.root_source_ref, "root_source_ref", maximum=4096),
        )
        object.__setattr__(
            self,
            "modality",
            _enum(self.modality, Modality, "modality"),
        )
        object.__setattr__(
            self,
            "kind",
            _enum(self.kind, SegmentKind, "kind"),
        )
        object.__setattr__(
            self,
            "sequence",
            _non_negative_int(self.sequence, "sequence"),
        )
        object.__setattr__(
            self,
            "content_digest",
            _sha256(self.content_digest, "content_digest"),
        )
        if not isinstance(self.locator, SegmentLocator):
            raise MultimodalError("locator must be SegmentLocator")
        object.__setattr__(
            self,
            "data_class",
            _token(self.data_class, "data_class", maximum=128, lower=True),
        )
        try:
            trust = TrustClass(self.trust_class)
        except ValueError as exc:
            raise MultimodalError("invalid trust_class") from exc
        object.__setattr__(self, "trust_class", trust)
        if self.sanitized_text is not None:
            if not isinstance(self.sanitized_text, str):
                raise MultimodalError("sanitized_text must be string")
            if len(self.sanitized_text) > 1_000_000:
                raise MultimodalError("sanitized_text exceeds bound")
        if not isinstance(self.findings, tuple):
            raise MultimodalError("findings must be tuple")
        normalized = tuple(
            sorted({_token(value, "finding", maximum=256) for value in self.findings})
        )
        object.__setattr__(self, "findings", normalized)

    @property
    def instruction_authority(self) -> bool:
        return False

    def payload(self) -> dict[str, object]:
        return {
            "schema": MULTIMODAL_SCHEMA,
            "kind": "modality-segment",
            "segment_id": self.segment_id,
            "artifact_id": self.artifact_id,
            "artifact_digest": self.artifact_digest,
            "root_source_ref": self.root_source_ref,
            "modality": self.modality.value,
            "segment_kind": self.kind.value,
            "sequence": self.sequence,
            "content_digest": self.content_digest,
            "locator_digest": self.locator.digest,
            "data_class": self.data_class,
            "trust_class": self.trust_class.value,
            "sanitized_text_digest": (
                None
                if self.sanitized_text is None
                else hashlib.sha256(
                    self.sanitized_text.encode("utf-8")
                ).hexdigest()
            ),
            "findings": list(self.findings),
            "instruction_authority": False,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class CrossModalReference:
    """Explicit alignment between two segments with shared source identity."""

    reference_id: str
    source_segment_id: str
    source_segment_digest: str
    target_segment_id: str
    target_segment_digest: str
    root_source_ref: str
    relation: CrossModalRelation
    confidence: float
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        for field in (
            "reference_id",
            "source_segment_id",
            "target_segment_id",
        ):
            object.__setattr__(
                self,
                field,
                _token(getattr(self, field), field, maximum=256),
            )
        for field in ("source_segment_digest", "target_segment_digest"):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        if self.source_segment_id == self.target_segment_id:
            raise MultimodalError("cross-modal reference cannot self-reference")
        object.__setattr__(
            self,
            "root_source_ref",
            _token(self.root_source_ref, "root_source_ref", maximum=4096),
        )
        object.__setattr__(
            self,
            "relation",
            _enum(self.relation, CrossModalRelation, "relation"),
        )
        object.__setattr__(
            self,
            "confidence",
            _unit(self.confidence, "confidence"),
        )
        if not isinstance(self.evidence_refs, tuple) or not self.evidence_refs:
            raise MultimodalError("cross-modal reference requires evidence_refs")
        refs = tuple(
            sorted({_token(ref, "evidence_ref", maximum=2048) for ref in self.evidence_refs})
        )
        object.__setattr__(self, "evidence_refs", refs)

    def payload(self) -> dict[str, object]:
        return {
            "schema": MULTIMODAL_SCHEMA,
            "kind": "cross-modal-reference",
            "reference_id": self.reference_id,
            "source_segment_id": self.source_segment_id,
            "source_segment_digest": self.source_segment_digest,
            "target_segment_id": self.target_segment_id,
            "target_segment_digest": self.target_segment_digest,
            "root_source_ref": self.root_source_ref,
            "relation": self.relation.value,
            "confidence": self.confidence,
            "evidence_refs": list(self.evidence_refs),
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.payload())


def media_artifact_id(
    *,
    root_source_ref: str,
    sha256: str,
    modality: Modality,
) -> str:
    root = _token(root_source_ref, "root_source_ref", maximum=4096)
    digest = _sha256(sha256, "sha256")
    mode = _enum(modality, Modality, "modality")
    return "media-" + canonical_digest(
        {
            "root_source_ref": root,
            "sha256": digest,
            "modality": mode.value,
        }
    )[:40]


def segment_id(
    *,
    artifact_id: str,
    sequence: int,
    kind: SegmentKind,
    content_digest: str,
) -> str:
    artifact = _token(artifact_id, "artifact_id", maximum=256)
    index = _non_negative_int(sequence, "sequence")
    segment_kind = _enum(kind, SegmentKind, "kind")
    content = _sha256(content_digest, "content_digest")
    return "segment-" + canonical_digest(
        {
            "artifact_id": artifact,
            "sequence": index,
            "kind": segment_kind.value,
            "content_digest": content,
        }
    )[:40]


__all__ = [
    "MULTIMODAL_SCHEMA",
    "CrossModalReference",
    "CrossModalRelation",
    "MediaArtifact",
    "MediaProvenance",
    "Modality",
    "ModalitySegment",
    "MultimodalError",
    "SegmentKind",
    "SegmentLocator",
    "TrustClass",
    "canonical_digest",
    "media_artifact_id",
    "segment_id",
]

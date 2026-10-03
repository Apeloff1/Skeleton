"""Content-addressed multimodal corpus and retrieval for P3-T2."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
from typing import Mapping, Sequence

from skeleton.ai.runtime.learning_foundation.data import ContentAddressedStore
from skeleton.ai.runtime.multimodal.intake import (
    Modality,
    MultimodalAsset,
    MultimodalIntake,
    MultimodalSanitizationError,
)


class MultimodalFoundationError(RuntimeError):
    """Multimodal identity, ordering or provenance cannot be proven."""


class LearningModality(str, Enum):
    DOCUMENT = "document"
    IMAGE = "image"
    AUDIO = "audio"
    LIVE_SPEECH = "live_speech"
    VIDEO = "video"


_BASE_MODALITY = {
    LearningModality.DOCUMENT: Modality.DOCUMENT,
    LearningModality.IMAGE: Modality.IMAGE,
    LearningModality.AUDIO: Modality.AUDIO,
    LearningModality.LIVE_SPEECH: Modality.AUDIO,
    LearningModality.VIDEO: Modality.VIDEO,
}
_TOKEN = re.compile(r"[\w-]+", re.UNICODE)


def _json(value: object) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise MultimodalFoundationError("value is not deterministic JSON") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _text(name: str, value: object, *, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MultimodalFoundationError(f"{name} must be non-empty text")
    result = value.strip()
    if len(result) > maximum:
        raise MultimodalFoundationError(f"{name} exceeds {maximum} characters")
    return result


def _sha(name: str, value: object) -> str:
    result = _text(name, value, maximum=64).lower()
    if len(result) != 64 or any(ch not in "0123456789abcdef" for ch in result):
        raise MultimodalFoundationError(f"{name} must be lowercase sha256")
    return result


def _refs(name: str, values: Sequence[str], *, minimum: int = 0) -> tuple[str, ...]:
    result: list[str] = []
    for raw in values:
        item = _text(name, raw)
        if item in result:
            raise MultimodalFoundationError(f"{name} contains duplicate {item}")
        result.append(item)
    if len(result) < minimum:
        raise MultimodalFoundationError(f"{name} requires at least {minimum} entries")
    return tuple(result)


@dataclass(frozen=True, slots=True)
class TextProjection:
    text_digest: str
    extractor_ref: str
    language: str
    instruction_trusted: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "text_digest", _sha("text_digest", self.text_digest))
        object.__setattr__(self, "extractor_ref", _text("extractor_ref", self.extractor_ref))
        object.__setattr__(self, "language", _text("language", self.language, maximum=64))
        if self.instruction_trusted is not False:
            raise MultimodalFoundationError("derived multimodal text never receives instruction authority")


@dataclass(frozen=True, slots=True)
class MultimodalRecord:
    record_id: str
    modality: LearningModality
    asset_digest: str
    media_type: str
    source_refs: tuple[str, ...]
    rights_refs: tuple[str, ...]
    lineage_refs: tuple[str, ...]
    simulated: bool
    embedded_instruction_detected: bool
    text_projection: TextProjection | None
    metadata: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "record_id", _text("record_id", self.record_id))
        object.__setattr__(self, "asset_digest", _sha("asset_digest", self.asset_digest))
        object.__setattr__(self, "media_type", _text("media_type", self.media_type, maximum=255).lower())
        object.__setattr__(self, "source_refs", _refs("source_ref", self.source_refs, minimum=1))
        object.__setattr__(self, "rights_refs", _refs("rights_ref", self.rights_refs, minimum=1))
        object.__setattr__(self, "lineage_refs", _refs("lineage_ref", self.lineage_refs))
        frozen = dict(self.metadata)
        _json(frozen)
        object.__setattr__(self, "metadata", frozen)

    @property
    def digest(self) -> str:
        return _digest(
            {
                "record_id": self.record_id,
                "modality": self.modality.value,
                "asset_digest": self.asset_digest,
                "media_type": self.media_type,
                "source_refs": list(self.source_refs),
                "rights_refs": list(self.rights_refs),
                "lineage_refs": list(self.lineage_refs),
                "simulated": self.simulated,
                "embedded_instruction_detected": self.embedded_instruction_detected,
                "text_projection": None if self.text_projection is None else {
                    "text_digest": self.text_projection.text_digest,
                    "extractor_ref": self.text_projection.extractor_ref,
                    "language": self.text_projection.language,
                    "instruction_trusted": False,
                },
                "metadata": dict(self.metadata),
            }
        )


@dataclass(frozen=True, slots=True)
class SpeechChunkReceipt:
    stream_id: str
    sequence: int
    record_digest: str
    previous_chunk_digest: str | None
    chain_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "stream_id", _text("stream_id", self.stream_id))
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence < 0:
            raise MultimodalFoundationError("speech sequence must be non-negative")
        object.__setattr__(self, "record_digest", _sha("record_digest", self.record_digest))
        if self.previous_chunk_digest is not None:
            object.__setattr__(self, "previous_chunk_digest", _sha("previous_chunk_digest", self.previous_chunk_digest))
        object.__setattr__(self, "chain_digest", _sha("chain_digest", self.chain_digest))


@dataclass(frozen=True, slots=True)
class RetrievalHit:
    record_id: str
    record_digest: str
    score: float
    source_refs: tuple[str, ...]
    simulated: bool


class MultimodalCorpus:
    def __init__(
        self,
        *,
        intake: MultimodalIntake | None = None,
        store: ContentAddressedStore | None = None,
    ) -> None:
        self.intake = intake or MultimodalIntake()
        self.store = store or ContentAddressedStore(max_object_bytes=512 * 1024 * 1024)
        self._records: dict[str, MultimodalRecord] = {}
        self._text: dict[str, str] = {}
        self._speech_tail: dict[str, SpeechChunkReceipt] = {}

    def ingest(
        self,
        *,
        record_id: str,
        modality: LearningModality,
        media_type: str,
        payload: bytes,
        source_refs: Sequence[str],
        rights_refs: Sequence[str],
        lineage_refs: Sequence[str] = (),
        metadata: Mapping[str, object] | None = None,
        extracted_text: str | None = None,
        extractor_ref: str | None = None,
        language: str = "und",
        simulated: bool = False,
    ) -> MultimodalRecord:
        rid = _text("record_id", record_id)
        try:
            asset = self.intake.sanitize(
                asset_id=rid,
                modality=_BASE_MODALITY[modality],
                mime_type=media_type,
                payload=payload,
                metadata=metadata,
            )
        except (KeyError, MultimodalSanitizationError) as exc:
            raise MultimodalFoundationError(str(exc)) from exc

        stored = self.store.put(payload, media_type=asset.mime_type)
        if stored.digest != asset.content_digest:
            raise MultimodalFoundationError("intake/store content identity drift")

        projection = None
        if extracted_text is not None:
            text = _text("extracted_text", extracted_text, maximum=2_000_000)
            extractor = _text("extractor_ref", extractor_ref)
            projection = TextProjection(
                text_digest=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                extractor_ref=extractor,
                language=language,
                instruction_trusted=False,
            )
            self._text[rid] = text
        elif extractor_ref is not None:
            raise MultimodalFoundationError("extractor_ref requires extracted_text")

        record = MultimodalRecord(
            record_id=rid,
            modality=modality,
            asset_digest=asset.content_digest,
            media_type=asset.mime_type,
            source_refs=tuple(source_refs),
            rights_refs=tuple(rights_refs),
            lineage_refs=tuple(lineage_refs),
            simulated=bool(simulated),
            embedded_instruction_detected=asset.embedded_instruction_detected,
            text_projection=projection,
            metadata=asset.sanitized_metadata,
        )
        prior = self._records.get(rid)
        if prior is not None and prior != record:
            raise MultimodalFoundationError("multimodal record identity conflict")
        self._records[rid] = record
        return record

    def ingest_speech_chunk(
        self,
        *,
        stream_id: str,
        sequence: int,
        payload: bytes,
        media_type: str,
        source_refs: Sequence[str],
        rights_refs: Sequence[str],
        transcript: str | None = None,
        extractor_ref: str | None = None,
    ) -> tuple[MultimodalRecord, SpeechChunkReceipt]:
        sid = _text("stream_id", stream_id)
        tail = self._speech_tail.get(sid)
        expected = 0 if tail is None else tail.sequence + 1
        if sequence != expected:
            raise MultimodalFoundationError(
                f"speech sequence gap: expected={expected} actual={sequence}"
            )
        record = self.ingest(
            record_id=f"{sid}:{sequence}",
            modality=LearningModality.LIVE_SPEECH,
            media_type=media_type,
            payload=payload,
            source_refs=source_refs,
            rights_refs=rights_refs,
            lineage_refs=(() if tail is None else (tail.record_digest,)),
            metadata={"source_id": sid},
            extracted_text=transcript,
            extractor_ref=extractor_ref,
            language="und",
        )
        previous = None if tail is None else tail.chain_digest
        payload_obj = {
            "stream_id": sid,
            "sequence": sequence,
            "record_digest": record.digest,
            "previous_chunk_digest": previous,
        }
        receipt = SpeechChunkReceipt(
            stream_id=sid,
            sequence=sequence,
            record_digest=record.digest,
            previous_chunk_digest=previous,
            chain_digest=_digest(payload_obj),
        )
        self._speech_tail[sid] = receipt
        return record, receipt

    def get(self, record_id: str) -> MultimodalRecord:
        return self._records[_text("record_id", record_id)]

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        include_simulated: bool = False,
    ) -> tuple[RetrievalHit, ...]:
        tokens = {token.casefold() for token in _TOKEN.findall(_text("query", query))}
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise MultimodalFoundationError("limit must be in [1, 100]")
        hits: list[RetrievalHit] = []
        for record_id, text in self._text.items():
            record = self._records[record_id]
            if record.simulated and not include_simulated:
                continue
            document_tokens = {token.casefold() for token in _TOKEN.findall(text)}
            overlap = len(tokens & document_tokens)
            if overlap == 0:
                continue
            score = overlap / max(1, len(tokens | document_tokens))
            hits.append(
                RetrievalHit(
                    record_id=record.record_id,
                    record_digest=record.digest,
                    score=score,
                    source_refs=record.source_refs,
                    simulated=record.simulated,
                )
            )
        hits.sort(key=lambda item: (-item.score, item.record_id))
        return tuple(hits[:limit])


__all__ = [
    "LearningModality",
    "MultimodalCorpus",
    "MultimodalFoundationError",
    "MultimodalRecord",
    "RetrievalHit",
    "SpeechChunkReceipt",
    "TextProjection",
]

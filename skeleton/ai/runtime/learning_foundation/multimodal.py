"""Content-addressed multimodal corpus and retrieval for P3-T2."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from copy import copy
from dataclasses import dataclass
from enum import Enum
from threading import RLock
from types import MappingProxyType

from skeleton.ai.runtime.learning_foundation.data import (
    ContentAddressedStore,
    DataPlaneError,
)
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
        if not isinstance(self.modality, LearningModality):
            raise MultimodalFoundationError("modality must be a LearningModality")
        if not isinstance(self.simulated, bool) or not isinstance(self.embedded_instruction_detected, bool):
            raise MultimodalFoundationError("record trust flags must be booleans")
        if self.text_projection is not None and not isinstance(self.text_projection, TextProjection):
            raise MultimodalFoundationError("text_projection must be a TextProjection")
        object.__setattr__(self, "asset_digest", _sha("asset_digest", self.asset_digest))
        object.__setattr__(self, "media_type", _text("media_type", self.media_type, maximum=255).lower())
        object.__setattr__(self, "source_refs", _refs("source_ref", self.source_refs, minimum=1))
        object.__setattr__(self, "rights_refs", _refs("rights_ref", self.rights_refs, minimum=1))
        object.__setattr__(self, "lineage_refs", _refs("lineage_ref", self.lineage_refs))
        frozen = dict(self.metadata)
        _json(frozen)
        # Intake admits scalar metadata. Keeping the same constraint here makes
        # the frozen record deeply immutable, including for direct constructors.
        if any(
            value is not None and not isinstance(value, (bool, int, float, str)) for value in frozen.values()
        ):
            raise MultimodalFoundationError("record metadata values must be scalar")
        object.__setattr__(self, "metadata", MappingProxyType(frozen))

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
                "text_projection": (
                    None
                    if self.text_projection is None
                    else {
                        "text_digest": self.text_projection.text_digest,
                        "extractor_ref": self.text_projection.extractor_ref,
                        "language": self.text_projection.language,
                        "instruction_trusted": self.text_projection.instruction_trusted,
                    }
                ),
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
            object.__setattr__(
                self, "previous_chunk_digest", _sha("previous_chunk_digest", self.previous_chunk_digest)
            )
        object.__setattr__(self, "chain_digest", _sha("chain_digest", self.chain_digest))
        expected = _digest(
            {
                "stream_id": self.stream_id,
                "sequence": self.sequence,
                "record_digest": self.record_digest,
                "previous_chunk_digest": self.previous_chunk_digest,
            }
        )
        if self.chain_digest != expected:
            raise MultimodalFoundationError("speech receipt chain identity drift")


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
        self._record_digests: dict[str, str] = {}
        self._text: dict[str, str] = {}
        self._speech_tail: dict[str, SpeechChunkReceipt] = {}
        self._speech_chunks: dict[tuple[str, int], SpeechChunkReceipt] = {}
        self._speech_chain_digests: dict[tuple[str, int], str] = {}
        self._speech_tail_sequences: dict[str, int] = {}
        self._speech_record_keys: dict[str, tuple[str, int]] = {}
        self._lock = RLock()

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
        with self._lock:
            return self._ingest(
                record_id=record_id,
                modality=modality,
                media_type=media_type,
                payload=payload,
                source_refs=source_refs,
                rights_refs=rights_refs,
                lineage_refs=lineage_refs,
                metadata=metadata,
                extracted_text=extracted_text,
                extractor_ref=extractor_ref,
                language=language,
                simulated=simulated,
            )

    def _ingest(
        self,
        *,
        record_id: str,
        modality: LearningModality,
        media_type: str,
        payload: bytes,
        source_refs: Sequence[str],
        rights_refs: Sequence[str],
        lineage_refs: Sequence[str],
        metadata: Mapping[str, object] | None,
        extracted_text: str | None,
        extractor_ref: str | None,
        language: str,
        simulated: bool,
    ) -> MultimodalRecord:
        rid = _text("record_id", record_id)
        if not isinstance(modality, LearningModality):
            raise MultimodalFoundationError("modality must be a LearningModality")
        if not isinstance(simulated, bool):
            raise MultimodalFoundationError("simulated must be a boolean")
        mime = _text("media_type", media_type, maximum=255)
        prior = self._records.get(rid)
        if prior is not None:
            self._verify_record(rid)

        # Both canonical witnesses are in-memory registries. Validate on isolated
        # copies so rejected records cannot publish an asset, blob or projection.
        staged_intake = copy(self.intake)
        staged_intake._assets = dict(self.intake._assets)
        try:
            asset = staged_intake.sanitize(
                asset_id=rid,
                modality=_BASE_MODALITY[modality],
                mime_type=mime,
                payload=payload,
                metadata=metadata,
            )
        except (KeyError, MultimodalSanitizationError) as exc:
            raise MultimodalFoundationError(str(exc)) from exc

        projection = None
        text = None
        if extracted_text is not None:
            text = _text("extracted_text", extracted_text, maximum=2_000_000)
            extractor = _text("extractor_ref", extractor_ref)
            projection = TextProjection(
                text_digest=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                extractor_ref=extractor,
                language=language,
                instruction_trusted=False,
            )
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
            simulated=simulated,
            embedded_instruction_detected=asset.embedded_instruction_detected,
            text_projection=projection,
            metadata=asset.sanitized_metadata,
        )
        if prior is not None and prior != record:
            raise MultimodalFoundationError("multimodal record identity conflict")

        if prior is not None:
            return prior

        staged_store = copy(self.store)
        staged_store._objects = dict(self.store._objects)
        staged_store._types = dict(self.store._types)
        try:
            stored = staged_store.put(payload, media_type=asset.mime_type)
            source = staged_store.get(stored.digest)
        except (DataPlaneError, KeyError, TypeError) as exc:
            raise MultimodalFoundationError("multimodal content storage failed") from exc
        if (
            stored.digest != asset.content_digest
            or stored.size_bytes != len(payload)
            or stored.media_type != asset.mime_type
            or source != payload
        ):
            raise MultimodalFoundationError("intake/store content identity drift")

        record_digest = record.digest
        self.intake._assets[rid] = asset
        self.store._objects[stored.digest] = staged_store._objects[stored.digest]
        self.store._types[stored.digest] = staged_store._types[stored.digest]
        self._records[rid] = record
        self._record_digests[rid] = record_digest
        if text is not None:
            self._text[rid] = text
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
        with self._lock:
            return self._ingest_speech_chunk(
                stream_id=stream_id,
                sequence=sequence,
                payload=payload,
                media_type=media_type,
                source_refs=source_refs,
                rights_refs=rights_refs,
                transcript=transcript,
                extractor_ref=extractor_ref,
            )

    def _ingest_speech_chunk(
        self,
        *,
        stream_id: str,
        sequence: int,
        payload: bytes,
        media_type: str,
        source_refs: Sequence[str],
        rights_refs: Sequence[str],
        transcript: str | None,
        extractor_ref: str | None,
    ) -> tuple[MultimodalRecord, SpeechChunkReceipt]:
        sid = _text("stream_id", stream_id)
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
            raise MultimodalFoundationError("speech sequence must be non-negative")
        tail = self._speech_tail.get(sid)
        if tail is not None:
            if not isinstance(tail, SpeechChunkReceipt):
                raise MultimodalFoundationError("speech tail identity drift")
            if self._speech_tail_sequences.get(sid) != tail.sequence:
                raise MultimodalFoundationError("speech tail identity drift")
            if self._verify_speech_receipt(sid, tail.sequence) != tail:
                raise MultimodalFoundationError("speech tail identity drift")
        elif sid in self._speech_tail_sequences:
            raise MultimodalFoundationError("speech tail is missing")

        prior_receipt = self._speech_chunks.get((sid, sequence))
        if prior_receipt is not None:
            self._verify_speech_receipt(sid, sequence)
            previous_receipt = self._speech_chunks.get((sid, sequence - 1))
        else:
            previous_receipt = tail
        expected = 0 if tail is None else tail.sequence + 1
        if prior_receipt is None and sequence != expected:
            raise MultimodalFoundationError(f"speech sequence gap: expected={expected} actual={sequence}")
        record = self.ingest(
            record_id=f"{sid}:{sequence}",
            modality=LearningModality.LIVE_SPEECH,
            media_type=media_type,
            payload=payload,
            source_refs=source_refs,
            rights_refs=rights_refs,
            lineage_refs=(() if previous_receipt is None else (previous_receipt.record_digest,)),
            metadata={"source_id": sid},
            extracted_text=transcript,
            extractor_ref=extractor_ref,
            language="und",
        )
        if prior_receipt is not None:
            return record, prior_receipt

        previous = None if previous_receipt is None else previous_receipt.chain_digest
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
        self._speech_chunks[(sid, sequence)] = receipt
        self._speech_chain_digests[(sid, sequence)] = receipt.chain_digest
        self._speech_tail_sequences[sid] = sequence
        self._speech_record_keys[record.record_id] = (sid, sequence)
        self._speech_tail[sid] = receipt
        return record, receipt

    def get(self, record_id: str) -> MultimodalRecord:
        with self._lock:
            rid = _text("record_id", record_id)
            record = self._verify_record(rid)
            speech_key = self._speech_record_keys.get(rid)
            if speech_key is None and record.modality is LearningModality.LIVE_SPEECH:
                stream_id, _, sequence = rid.rpartition(":")
                if sequence.isascii() and sequence.isdecimal():
                    candidate_key = (stream_id, int(sequence))
                    if candidate_key in self._speech_chunks:
                        speech_key = candidate_key
            if speech_key is not None:
                self._verify_speech_receipt(*speech_key)
            return record

    def _verify_record(self, record_id: str) -> MultimodalRecord:
        record = self._records[record_id]
        if not isinstance(record, MultimodalRecord):
            raise MultimodalFoundationError("multimodal record identity drift")
        try:
            record_digest = record.digest
        except (AttributeError, TypeError, ValueError) as exc:
            raise MultimodalFoundationError("multimodal record identity drift") from exc
        if record.record_id != record_id or self._record_digests.get(record_id) != record_digest:
            raise MultimodalFoundationError("multimodal record identity drift")
        try:
            source = self.store.get(record.asset_digest)
        except (DataPlaneError, KeyError) as exc:
            raise MultimodalFoundationError("multimodal source content integrity failed") from exc
        if not isinstance(source, bytes):
            raise MultimodalFoundationError("multimodal source content integrity failed")
        asset = self.intake._assets.get(record_id)
        if (
            not isinstance(asset, MultimodalAsset)
            or asset.asset_id != record_id
            or asset.modality != _BASE_MODALITY[record.modality]
            or asset.content_digest != record.asset_digest
            or asset.mime_type != record.media_type
            or self.store._types.get(record.asset_digest) != record.media_type
            or asset.size_bytes != len(source)
            or asset.instruction_trusted is not False
            or asset.embedded_instruction_detected != record.embedded_instruction_detected
            or dict(asset.sanitized_metadata) != dict(record.metadata)
        ):
            raise MultimodalFoundationError("multimodal source provenance drift")
        text = self._text.get(record_id)
        if record.text_projection is None:
            if text is not None or record_id in self._text:
                raise MultimodalFoundationError("unissued multimodal text projection")
        elif (
            not isinstance(text, str)
            or hashlib.sha256(text.encode("utf-8")).hexdigest() != record.text_projection.text_digest
        ):
            raise MultimodalFoundationError("multimodal text projection integrity failed")
        return record

    def _verify_speech_receipt(self, stream_id: str, sequence: int) -> SpeechChunkReceipt:
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
            raise MultimodalFoundationError("speech receipt identity drift")
        previous = None
        for chunk_sequence in range(sequence + 1):
            key = (stream_id, chunk_sequence)
            receipt = self._speech_chunks.get(key)
            if not isinstance(receipt, SpeechChunkReceipt):
                raise MultimodalFoundationError("speech receipt is missing")
            expected = _digest(
                {
                    "stream_id": stream_id,
                    "sequence": chunk_sequence,
                    "record_digest": receipt.record_digest,
                    "previous_chunk_digest": receipt.previous_chunk_digest,
                }
            )
            if (
                receipt.stream_id != stream_id
                or isinstance(receipt.sequence, bool)
                or not isinstance(receipt.sequence, int)
                or receipt.sequence != chunk_sequence
                or receipt.chain_digest != expected
                or self._speech_chain_digests.get(key) != receipt.chain_digest
            ):
                raise MultimodalFoundationError("speech receipt identity drift")
            try:
                record = self._verify_record(f"{stream_id}:{chunk_sequence}")
            except KeyError as exc:
                raise MultimodalFoundationError("speech source record is missing") from exc
            if (
                receipt.record_digest != record.digest
                or receipt.previous_chunk_digest != (None if previous is None else previous.chain_digest)
                or record.lineage_refs != (() if previous is None else (previous.record_digest,))
                or self._speech_record_keys.get(record.record_id) != key
            ):
                raise MultimodalFoundationError("speech receipt provenance drift")
            previous = receipt
        return receipt

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        include_simulated: bool = False,
    ) -> tuple[RetrievalHit, ...]:
        with self._lock:
            return self._search(query, limit=limit, include_simulated=include_simulated)

    def _search(
        self,
        query: str,
        *,
        limit: int,
        include_simulated: bool,
    ) -> tuple[RetrievalHit, ...]:
        tokens = {token.casefold() for token in _TOKEN.findall(_text("query", query))}
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise MultimodalFoundationError("limit must be in [1, 100]")
        if not isinstance(include_simulated, bool):
            raise MultimodalFoundationError("include_simulated must be a boolean")
        if self._text.keys() - self._records.keys():
            raise MultimodalFoundationError("orphan multimodal text projection")
        if self._speech_tail.keys() != self._speech_tail_sequences.keys():
            raise MultimodalFoundationError("speech tail identity drift")
        for stream_id, tail in self._speech_tail.items():
            if (
                not isinstance(tail, SpeechChunkReceipt)
                or tail.sequence != self._speech_tail_sequences[stream_id]
                or self._verify_speech_receipt(stream_id, tail.sequence) != tail
            ):
                raise MultimodalFoundationError("speech tail identity drift")
        hits: list[RetrievalHit] = []
        for record_id in self._records:
            record = self._verify_record(record_id)
            if record.simulated and not include_simulated:
                continue
            if record.text_projection is None:
                continue
            text = self._text[record_id]
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

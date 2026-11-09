"""Bounded execution bridges for existing speech and video evidence contracts.

Transcripts and container offsets are caller declarations. Verified media proves
actual source/decoded bytes and measurements, never ASR or video decoding.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import math
from collections.abc import Callable, Mapping, Sequence
from copy import copy
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from skeleton.ai.runtime.extensions.multimodal import (
    SpeechFrame,
    SpeechSession,
    TranscriptSegment,
)
from skeleton.ai.runtime.multimodal.intake import VerifiedMultimodalAsset

from .multimodal import (
    _TOKEN,
    LearningModality,
    MultimodalCorpus,
    MultimodalFoundationError,
    MultimodalTrainingManifest,
    _digest,
    _json,
    _ordered_refs,
    _sha,
    _text,
)

if TYPE_CHECKING:
    from skeleton.ai.runtime.training.data import (
        DatasetRegistry,
        MaterializedDatasetReceipt,
    )

_SCHEMA = "skeleton.ai.multimodal_temporal_execution.v1"


def _integer(name: str, value: object, ceiling: int, *, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= ceiling:
        raise MultimodalFoundationError(f"{name} must be an integer in [{minimum}, {ceiling}]")
    return value


def _seconds(name: str, value: object) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        raise MultimodalFoundationError(f"{name} must be finite nonnegative seconds")
    return float(value)


def _bounded_refs(name: str, values: Sequence[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence) or len(values) > 128:
        raise MultimodalFoundationError(f"{name} requires at most 128 ordered references")
    return _ordered_refs(name, values)


def _clone_corpus(corpus: MultimodalCorpus) -> MultimodalCorpus:
    staged = copy(corpus)
    for name, value in vars(corpus).items():
        if isinstance(value, dict):
            setattr(staged, name, dict(value))
    staged.intake = copy(corpus.intake)
    staged.intake._assets = dict(corpus.intake._assets)
    staged.store = copy(corpus.store)
    staged.store._objects = dict(corpus.store._objects)
    staged.store._types = dict(corpus.store._types)
    return staged


def _publish_corpus(source: MultimodalCorpus, target: MultimodalCorpus) -> None:
    for name, value in vars(source).items():
        if isinstance(value, dict):
            setattr(target, name, value)
    target.intake._assets = source.intake._assets
    target.store._objects = source.store._objects
    target.store._types = source.store._types


@dataclass(frozen=True, slots=True)
class SpeechFrameEvidence:
    frame: SpeechFrame
    end_seconds: float
    record_id: str
    record_digest: str
    validation_digest: str
    previous_digest: str | None

    @property
    def digest(self) -> str:
        return _digest(asdict(self))


@dataclass(frozen=True, slots=True)
class SpeechExecutionReceipt:
    command_id: str
    request_digest: str
    state_digest: str
    state: str
    frame_count: int
    final_count: int
    version: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "command_id", _text("command_id", self.command_id, maximum=128))
        object.__setattr__(self, "request_digest", _sha("request_digest", self.request_digest))
        object.__setattr__(self, "state_digest", _sha("state_digest", self.state_digest))
        if self.state not in SpeechSession._ALLOWED:
            raise MultimodalFoundationError("speech receipt state is invalid")
        _integer("frame_count", self.frame_count, 128, minimum=0)
        _integer("final_count", self.final_count, self.frame_count, minimum=0)
        _integer("version", self.version, 512)

    @property
    def digest(self) -> str:
        return _digest(asdict(self))


class LiveSpeechExecution:
    """Execute the existing SpeechSession over verified PCM and issued evidence.

    Optional recovery snapshots are separately consented immutable copies. The
    DatasetRegistry authority of each stable copied frame governs recovery;
    external source systems are not observed or granted training authority.
    """

    def __init__(
        self,
        corpus: MultimodalCorpus,
        session_id: str,
        *,
        source_refs: Sequence[str],
        rights_refs: Sequence[str],
        registry: DatasetRegistry | None = None,
        recovery_rights_policy: Mapping[str, Sequence[str]] | None = None,
        dataset_id: str | None = None,
        max_frames: int = 128,
        max_frame_bytes: int = 65536,
        max_total_bytes: int = 8388608,
        max_pending_frames: int = 32,
        max_commands: int = 512,
        acquired_at: datetime | None = None,
    ) -> None:
        if not isinstance(corpus, MultimodalCorpus):
            raise MultimodalFoundationError("speech execution requires the canonical corpus")
        self.corpus = corpus
        self._source_refs = _bounded_refs("source_ref", source_refs)
        self._rights_refs = _bounded_refs("rights_ref", rights_refs)
        self._limits = {
            "max_frames": _integer("max_frames", max_frames, 128),
            "max_frame_bytes": _integer("max_frame_bytes", max_frame_bytes, 65536),
            "max_total_bytes": _integer("max_total_bytes", max_total_bytes, 8388608),
            "max_pending_frames": _integer("max_pending_frames", max_pending_frames, 32),
            "max_commands": _integer("max_commands", max_commands, 512),
        }
        self._session = SpeechSession(_text("session_id", session_id, maximum=128), max_segments=max_frames)
        self._registry = registry
        self._dataset_id = _text("dataset_id", dataset_id or f"speech-session:{self._session.session_id}")
        self._recovery_policy: dict[str, tuple[str, ...]] = {}
        if registry is not None:
            from skeleton.ai.runtime.training.data import DatasetRegistry

            if not isinstance(registry, DatasetRegistry):
                raise MultimodalFoundationError("speech recovery requires the canonical governed registry")
            if not isinstance(recovery_rights_policy, Mapping) or len(recovery_rights_policy) > 128:
                raise MultimodalFoundationError("durable speech requires explicit bounded recovery rights")
            self._recovery_policy = {
                _text("rights_ref", ref): _ordered_refs("recovery_use", uses)
                for ref, uses in recovery_rights_policy.items()
            }
            if any("speech_recovery" not in self._recovery_policy.get(ref, ()) for ref in self._rights_refs):
                raise MultimodalFoundationError("every source right must explicitly permit speech recovery")
            if registry.latest_materialized_version(self._dataset_id) != 0:
                raise MultimodalFoundationError("existing speech recovery namespace must be restored")
        elif recovery_rights_policy is not None or dataset_id is not None:
            raise MultimodalFoundationError("recovery configuration requires a governed registry")
        when = acquired_at or datetime.now(UTC)
        if not isinstance(when, datetime) or when.tzinfo is None or when.utcoffset() is None:
            raise MultimodalFoundationError("acquired_at must be timezone aware")
        self._acquired_at = when.astimezone(UTC)
        self._frames: tuple[SpeechFrameEvidence, ...] = ()
        self._extractors: tuple[str, ...] = ()
        self._final_record_ids: tuple[str, ...] = ()
        self._commands: dict[str, SpeechExecutionReceipt] = {}
        self._requests: dict[str, dict[str, object]] = {}
        self._version = 0
        self._checkpoint: MaterializedDatasetReceipt | None = None
        self._checkpoint_digest: str | None = None
        self._integrity_digest = _digest(self._metadata())

    @property
    def session(self) -> SpeechSession:
        view = copy(self._session)
        view._segments = list(self._session.segments)
        return view

    @property
    def frames(self) -> tuple[SpeechFrameEvidence, ...]:
        return self._frames

    @property
    def final_record_ids(self) -> tuple[str, ...]:
        return self._final_record_ids

    @property
    def checkpoint(self) -> MaterializedDatasetReceipt | None:
        return self._checkpoint

    def _metadata(self) -> dict[str, object]:
        return {
            "schema_version": _SCHEMA,
            "kind": "session",
            "session_id": self._session.session_id,
            "state": self._session.state,
            "source_refs": list(self._source_refs),
            "rights_refs": list(self._rights_refs),
            "limits": dict(self._limits),
            "dataset_id": self._dataset_id,
            "recovery_rights_policy": {key: list(value) for key, value in self._recovery_policy.items()},
            "acquired_at": self._acquired_at.isoformat(),
            "frames": [asdict(frame) for frame in self._frames],
            "segments": [asdict(segment) for segment in self._session.segments],
            "extractors": list(self._extractors),
            "final_record_ids": list(self._final_record_ids),
            "commands": {key: asdict(value) for key, value in self._commands.items()},
            "requests": {key: dict(value) for key, value in self._requests.items()},
            "version": self._version,
        }

    def _verify(self) -> None:
        if self._integrity_digest != _digest(self._metadata()):
            raise MultimodalFoundationError("speech execution evidence drift")
        for evidence in self._frames:
            record = self.corpus.get(evidence.record_id)
            asset = self.corpus.intake._assets[evidence.record_id]
            if (
                record.digest != evidence.record_digest
                or not isinstance(asset, VerifiedMultimodalAsset)
                or asset.validation.digest != evidence.validation_digest
                or record.asset_digest != evidence.frame.payload_digest
            ):
                raise MultimodalFoundationError("speech frame evidence drift")
        if self._final_record_ids:
            # The issued tail walks and verifies the entire original speech
            # chain; re-walking each prefix would make session replay quadratic.
            self.corpus.get(self._final_record_ids[-1])
        if self._registry is not None:
            if self._registry.latest_materialized_version(self._dataset_id) != self._version:
                raise MultimodalFoundationError("stale speech recovery version")
            if self._checkpoint is not None:
                if self._checkpoint.digest != self._checkpoint_digest:
                    raise MultimodalFoundationError("issued speech recovery checkpoint identity drift")
                self._registry.materialized_sources(self._checkpoint.dataset_digest)
            elif self._version:
                raise MultimodalFoundationError("issued speech recovery checkpoint is missing")

    def _persist(self) -> None:
        if self._registry is None:
            return
        # Lazy import preserves the existing training/foundation import boundary.
        from skeleton.ai.runtime.training.data import (
            IngestEnvelope,
            MaterializedTrainingSource,
        )

        documents = [_json(self._metadata())]
        documents.extend(
            _json(
                {
                    "schema_version": _SCHEMA,
                    "kind": "frame",
                    "session_id": self._session.session_id,
                    "evidence": asdict(evidence),
                    "payload_base64": base64.b64encode(
                        self.corpus.store.get(evidence.frame.payload_digest)
                    ).decode("ascii"),
                    "source_refs": list(self._source_refs),
                    "rights_refs": list(self._rights_refs),
                }
            )
            for evidence in self._frames
        )
        sources = []
        for document in documents:
            if len(document.encode("utf-8")) > 1024 * 1024:
                raise MultimodalFoundationError("speech recovery document exceeds byte ceiling")
            payload = _json([document]).encode("utf-8")
            envelope = IngestEnvelope.from_bytes(
                source_id="speech-recovery:" + hashlib.sha256(payload).hexdigest(),
                payload=payload,
                parser_version="live-speech-recovery@1",
                classification="internal",
                rights=("speech_recovery",),
                trusted=True,
                acquired_at=self._acquired_at,
            )
            sources.append(
                MaterializedTrainingSource(
                    envelope,
                    payload,
                    "json_documents",
                    self._rights_refs,
                    self._source_refs,
                    {
                        "speech_session_id": self._session.session_id,
                        "recovery_consent_digest": _digest(self._recovery_policy),
                    },
                )
            )
        self._checkpoint = self._registry.ingest_materialized(
            ingestion_id=f"speech-recovery:{self._session.session_id}:{self._version}",
            dataset_id=self._dataset_id,
            expected_version=self._version - 1,
            sources={"snapshot": tuple(sources)},
            classification="internal",
            permitted_uses=("speech_recovery",),
            retention_class="bounded-speech-recovery",
        )
        self._checkpoint_digest = self._checkpoint.digest

    def _apply(
        self, command_id: str, request: Mapping[str, object], action: Callable[[LiveSpeechExecution], None]
    ) -> SpeechExecutionReceipt:
        cid = _text("command_id", command_id, maximum=128)
        request_digest = _digest(request)
        with self.corpus._lock:
            self._verify()
            prior = self._commands.get(cid)
            if prior is not None:
                if prior.request_digest != request_digest:
                    raise MultimodalFoundationError("speech command identity conflict")
                return prior
            if len(self._commands) >= self._limits["max_commands"]:
                raise MultimodalFoundationError("speech command backpressure limit reached")
            candidate = copy(self)
            candidate.corpus = _clone_corpus(self.corpus)
            candidate._session = self.session
            candidate._commands = dict(self._commands)
            candidate._requests = dict(self._requests)
            try:
                action(candidate)
            except (ValueError, BufferError) as exc:
                raise MultimodalFoundationError(str(exc)) from exc
            candidate._version += 1
            receipt = SpeechExecutionReceipt(
                cid,
                request_digest,
                _digest(candidate._metadata()),
                candidate._session.state,
                len(candidate._frames),
                len(candidate._final_record_ids),
                candidate._version,
            )
            candidate._commands[cid] = receipt
            candidate._requests[cid] = dict(request)
            candidate._integrity_digest = _digest(candidate._metadata())
            candidate._persist()
            _publish_corpus(candidate.corpus, self.corpus)
            for name, value in vars(candidate).items():
                if name != "corpus":
                    setattr(self, name, value)
            return receipt

    def transition(self, state: str, *, command_id: str) -> SpeechExecutionReceipt:
        target = _text("state", state)

        def action(candidate: LiveSpeechExecution) -> None:
            if target == "closed" and len(candidate._final_record_ids) != len(candidate._frames):
                raise MultimodalFoundationError("closing speech requires every frame finalized")
            candidate._session.transition(target)

        return self._apply(command_id, {"operation": "transition", "state": target}, action)

    def append_frame(
        self, *, sequence: int, start_seconds: float, payload: bytes, command_id: str
    ) -> SpeechExecutionReceipt:
        seq = _integer("sequence", sequence, 127, minimum=0)
        start = _seconds("start_seconds", start_seconds)
        if not isinstance(payload, bytes) or not 1 <= len(payload) <= self._limits["max_frame_bytes"]:
            raise MultimodalFoundationError("speech frame exceeds immutable source byte bound")

        def action(candidate: LiveSpeechExecution) -> None:
            if candidate._session.state != "active":
                raise MultimodalFoundationError("speech frames require an active session")
            if seq != len(candidate._frames):
                raise MultimodalFoundationError("speech frame sequence gap or duplicate")
            if seq >= candidate._limits["max_frames"]:
                raise MultimodalFoundationError("speech frame backpressure limit reached")
            if seq - len(candidate._final_record_ids) >= candidate._limits["max_pending_frames"]:
                raise MultimodalFoundationError("speech pending-frame backpressure limit reached")
            total = sum(
                len(candidate.corpus.store.get(item.frame.payload_digest)) for item in candidate._frames
            )
            if total + len(payload) > candidate._limits["max_total_bytes"]:
                raise MultimodalFoundationError("speech aggregate source byte budget exceeded")
            expected_start = 0.0 if not candidate._frames else candidate._frames[-1].end_seconds
            if start != expected_start:
                raise MultimodalFoundationError("speech frame timestamp gap or overlap")
            rid = f"speech-frame:{candidate._session.session_id}:{seq}"
            record = candidate.corpus.ingest(
                record_id=rid,
                modality=LearningModality.LIVE_SPEECH,
                media_type="audio/wav",
                payload=payload,
                source_refs=candidate._source_refs,
                rights_refs=candidate._rights_refs,
                lineage_refs=(() if not candidate._frames else (candidate._frames[-1].record_digest,)),
                metadata={"source_id": candidate._session.session_id},
                verified=True,
            )
            asset = candidate.corpus.intake._assets[rid]
            assert isinstance(asset, VerifiedMultimodalAsset)
            measured = asset.validation
            if not measured.sample_count or not measured.sample_rate_hz:
                raise MultimodalFoundationError("speech frames require nonempty measured PCM samples")
            if candidate._frames:
                previous = candidate.corpus.intake._assets[candidate._frames[-1].record_id].validation
                if (measured.sample_rate_hz, measured.channels, measured.sample_width_bytes) != (
                    previous.sample_rate_hz,
                    previous.channels,
                    previous.sample_width_bytes,
                ):
                    raise MultimodalFoundationError("speech PCM format changed within session")
            # Cumulative integer sample counts avoid duration-addition drift.
            count = sum(
                candidate.corpus.intake._assets[item.record_id].validation.sample_count
                for item in candidate._frames
            )
            end = (count + measured.sample_count) / measured.sample_rate_hz
            frame = SpeechFrame(candidate._session.session_id, seq, start, record.asset_digest)
            candidate._frames += (
                SpeechFrameEvidence(
                    frame,
                    end,
                    rid,
                    record.digest,
                    measured.digest,
                    None if not candidate._frames else candidate._frames[-1].digest,
                ),
            )

        return self._apply(
            command_id,
            {
                "operation": "frame",
                "sequence": seq,
                "start_seconds": start,
                "payload_digest": hashlib.sha256(payload).hexdigest(),
            },
            action,
        )

    def submit_transcript(
        self, segment: TranscriptSegment, *, extractor_ref: str, command_id: str
    ) -> SpeechExecutionReceipt:
        if not isinstance(segment, TranscriptSegment):
            raise MultimodalFoundationError("speech declarations require TranscriptSegment")
        seq = _integer("sequence", segment.sequence, 127, minimum=0)
        if not isinstance(segment.final, bool):
            raise MultimodalFoundationError("transcript final flag must be boolean")
        text = _text("transcript", segment.text, maximum=16384)
        extractor = _text("extractor_ref", extractor_ref)
        start, end = _seconds("start_seconds", segment.start_seconds), _seconds(
            "end_seconds", segment.end_seconds
        )
        declaration = TranscriptSegment(segment.session_id, seq, text, start, end, segment.final)

        def action(candidate: LiveSpeechExecution) -> None:
            if candidate._session.state != "active":
                raise MultimodalFoundationError("speech declarations require an active session")
            if (
                declaration.session_id != candidate._session.session_id
                or seq != len(candidate._final_record_ids)
                or seq >= len(candidate._frames)
            ):
                raise MultimodalFoundationError("transcript must target the next issued speech frame")
            evidence = candidate._frames[seq]
            if (start, end) != (evidence.frame.timestamp_seconds, evidence.end_seconds):
                raise MultimodalFoundationError("transcript offsets do not match measured PCM frame")
            provisional = len(candidate._session.segments) > len(candidate._final_record_ids)
            if provisional and not declaration.final:
                candidate._session.replace_provisional(declaration)
                candidate._extractors = (*candidate._extractors[:-1], extractor)
            else:
                if provisional:
                    # Existing SpeechSession has no finalization helper: replay
                    # its issued final prefix, then append the finalized segment.
                    candidate._session._segments = list(candidate._session.segments[:-1])
                    candidate._extractors = candidate._extractors[:-1]
                candidate._session.append(declaration)
                candidate._extractors += (extractor,)
            if declaration.final:
                record, _ = candidate.corpus.ingest_speech_chunk(
                    stream_id=f"live:{candidate._session.session_id}",
                    sequence=seq,
                    payload=candidate.corpus.store.get(evidence.frame.payload_digest),
                    media_type="audio/wav",
                    source_refs=candidate._source_refs,
                    rights_refs=candidate._rights_refs,
                    transcript=text,
                    extractor_ref=extractor,
                    verified=True,
                    lineage_refs=(evidence.record_digest, evidence.digest),
                )
                candidate._final_record_ids += (record.record_id,)

        return self._apply(
            command_id,
            {"operation": "transcript", "segment": asdict(declaration), "extractor_ref": extractor},
            action,
        )

    def export_final_text(
        self, *, export_id: str, purpose: str, rights_policy: Mapping[str, Sequence[str]]
    ) -> tuple[MultimodalTrainingManifest, tuple[str, ...]]:
        with self.corpus._lock:
            self._verify()
            return self.corpus.export_text_training(
                self._final_record_ids, export_id=export_id, purpose=purpose, rights_policy=rights_policy
            )

    @classmethod
    def restore(
        cls, corpus: MultimodalCorpus, registry: DatasetRegistry, dataset_digest: str
    ) -> LiveSpeechExecution:
        try:
            return cls._restore(corpus, registry, dataset_digest)
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as exc:
            raise MultimodalFoundationError("speech recovery evidence invalid") from exc

    @classmethod
    def _restore(
        cls, corpus: MultimodalCorpus, registry: DatasetRegistry, dataset_digest: str
    ) -> LiveSpeechExecution:
        digest = _sha("dataset_digest", dataset_digest)
        manifest = registry.dataset(digest)
        if manifest.permitted_uses != ("speech_recovery",) or tuple(
            split.name for split in manifest.splits
        ) != ("snapshot",):
            raise MultimodalFoundationError("dataset is not an isolated speech recovery snapshot")
        sources = registry.materialized_sources(digest)
        if not 1 <= len(sources) <= 129:
            raise MultimodalFoundationError("speech recovery source count exceeds bounds")
        documents = []
        import json

        for source in sources:
            if source.envelope.parser_version != "live-speech-recovery@1" or source.envelope.rights != (
                "speech_recovery",
            ):
                raise MultimodalFoundationError("speech recovery source authority mismatch")
            docs = source.documents()
            if len(docs) != 1 or len(docs[0].encode("utf-8")) > 1024 * 1024:
                raise MultimodalFoundationError("speech recovery document bounds invalid")
            decoded = json.loads(docs[0])
            if not isinstance(decoded, dict) or _json(decoded) != docs[0]:
                raise MultimodalFoundationError("speech recovery document must be a canonical object")
            documents.append(decoded)
        metadata = documents[0]
        if metadata.get("schema_version") != _SCHEMA or metadata.get("kind") != "session":
            raise MultimodalFoundationError("speech recovery session schema mismatch")
        version = _integer("version", metadata.get("version"), 512)
        if (
            manifest.version != str(version)
            or registry.latest_materialized_version(manifest.dataset_id) != version
        ):
            raise MultimodalFoundationError("stale speech recovery snapshot")
        # Construct off to the side so a rejected snapshot never poisons caller corpus.
        with corpus._lock:
            staged = _clone_corpus(corpus)
            recovered = cls(
                staged,
                metadata["session_id"],
                source_refs=metadata["source_refs"],
                rights_refs=metadata["rights_refs"],
                **metadata["limits"],
                acquired_at=datetime.fromisoformat(metadata["acquired_at"]),
            )
            recovered._dataset_id = metadata["dataset_id"]
            recovered._recovery_policy = {
                key: tuple(value) for key, value in metadata["recovery_rights_policy"].items()
            }
            if recovered._dataset_id != manifest.dataset_id or any(
                "speech_recovery" not in recovered._recovery_policy.get(ref, ())
                for ref in recovered._rights_refs
            ):
                raise MultimodalFoundationError("speech recovery consent mismatch")
            for source in sources:
                if (
                    source.rights_refs != recovered._rights_refs
                    or source.lineage_refs != recovered._source_refs
                    or source.envelope.source_id
                    != "speech-recovery:" + hashlib.sha256(source.payload).hexdigest()
                    or source.envelope.acquired_at != recovered._acquired_at.isoformat()
                    or dict(source.evidence)
                    != {
                        "speech_session_id": recovered._session.session_id,
                        "recovery_consent_digest": _digest(recovered._recovery_policy),
                    }
                ):
                    raise MultimodalFoundationError(
                        "speech recovery copied-source consent/provenance mismatch"
                    )
            recovered._integrity_digest = _digest(recovered._metadata())
            frame_documents = documents[1:]
            if len(frame_documents) != len(metadata["frames"]):
                raise MultimodalFoundationError("speech recovery frame coverage mismatch")
            payloads = []
            for index, document in enumerate(frame_documents):
                if (
                    document.get("kind") != "frame"
                    or document.get("schema_version") != _SCHEMA
                    or document.get("session_id") != recovered._session.session_id
                ):
                    raise MultimodalFoundationError("speech recovery frame schema mismatch")
                if document.get("source_refs") != list(recovered._source_refs) or document.get(
                    "rights_refs"
                ) != list(recovered._rights_refs):
                    raise MultimodalFoundationError("speech recovery original provenance mismatch")
                encoded = document.get("payload_base64")
                if not isinstance(encoded, str) or len(encoded) > 4 * math.ceil(
                    recovered._limits["max_frame_bytes"] / 3
                ):
                    raise MultimodalFoundationError("speech recovery PCM byte bound invalid")
                try:
                    payload = base64.b64decode(encoded, validate=True)
                except (binascii.Error, ValueError) as exc:
                    raise MultimodalFoundationError("speech recovery PCM encoding invalid") from exc
                if document.get("evidence") != metadata["frames"][index]:
                    raise MultimodalFoundationError("speech recovery frame receipt mismatch")
                payloads.append(payload)
            stored_commands = {
                key: SpeechExecutionReceipt(**value) for key, value in metadata["commands"].items()
            }
            requests = metadata["requests"]
            if (
                not isinstance(requests, dict)
                or len(stored_commands) != version
                or set(requests) != set(stored_commands)
                or version > recovered._limits["max_commands"]
            ):
                raise MultimodalFoundationError("speech recovery command coverage invalid")
            ordered = sorted(stored_commands.values(), key=lambda item: item.version)
            if [item.version for item in ordered] != list(range(1, version + 1)):
                raise MultimodalFoundationError("speech recovery command versions are not contiguous")
            for issued in ordered:
                cid = issued.command_id
                if stored_commands.get(cid) != issued:
                    raise MultimodalFoundationError("speech recovery command identity invalid")
                request = requests[cid]
                if not isinstance(request, dict) or _digest(request) != issued.request_digest:
                    raise MultimodalFoundationError("speech recovery command request identity drift")
                operation = request.get("operation")
                if operation == "transition" and set(request) == {"operation", "state"}:
                    actual = recovered.transition(request["state"], command_id=cid)
                elif operation == "frame" and set(request) == {
                    "operation",
                    "sequence",
                    "start_seconds",
                    "payload_digest",
                }:
                    seq = _integer("sequence", request["sequence"], len(payloads) - 1, minimum=0)
                    payload = payloads[seq]
                    if hashlib.sha256(payload).hexdigest() != request["payload_digest"]:
                        raise MultimodalFoundationError("speech recovery frame command source drift")
                    actual = recovered.append_frame(
                        sequence=seq, start_seconds=request["start_seconds"], payload=payload, command_id=cid
                    )
                elif operation == "transcript" and set(request) == {"operation", "segment", "extractor_ref"}:
                    actual = recovered.submit_transcript(
                        TranscriptSegment(**request["segment"]),
                        extractor_ref=request["extractor_ref"],
                        command_id=cid,
                    )
                else:
                    raise MultimodalFoundationError("speech recovery command schema invalid")
                if actual != issued:
                    raise MultimodalFoundationError("speech recovery command replay evidence drift")
            if [asdict(item) for item in recovered.frames] != metadata["frames"]:
                raise MultimodalFoundationError("speech recovery decoded frame identity drift")
            recovered._registry = registry
            recovered._checkpoint = registry.materialized_ingestion(
                f"speech-recovery:{recovered._session.session_id}:{version}"
            )
            if (
                recovered._checkpoint is None
                or recovered._checkpoint.dataset_digest != digest
                or recovered._metadata() != metadata
            ):
                raise MultimodalFoundationError("speech recovery issued snapshot identity mismatch")
            recovered._integrity_digest = _digest(recovered._metadata())
            recovered._checkpoint_digest = recovered._checkpoint.digest
            recovered._verify()
            _publish_corpus(staged, corpus)
            recovered.corpus = corpus
            return recovered


@dataclass(frozen=True, slots=True)
class TimedMediaFragment:
    record_id: str
    start_seconds: float
    end_seconds: float
    source_frame_index: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "record_id", _text("record_id", self.record_id))
        start = _seconds("start_seconds", self.start_seconds)
        end = _seconds("end_seconds", self.end_seconds)
        if end < start:
            raise MultimodalFoundationError("video fragment timestamps are reversed")
        object.__setattr__(self, "start_seconds", start)
        object.__setattr__(self, "end_seconds", end)
        if self.source_frame_index is not None:
            _integer("source_frame_index", self.source_frame_index, 1_000_000, minimum=0)


@dataclass(frozen=True, slots=True)
class VideoFragmentEvidence:
    fragment: TimedMediaFragment
    modality: LearningModality
    record_digest: str
    asset_digest: str
    projection_digest: str
    validation_digest: str
    rights_refs: tuple[str, ...]
    source_refs: tuple[str, ...]
    lineage_refs: tuple[str, ...]

    @property
    def digest(self) -> str:
        return _digest(asdict(self))


@dataclass(frozen=True, slots=True)
class VideoTimelineReceipt:
    timeline_id: str
    parent_record_id: str
    parent_record_digest: str
    parent_asset_digest: str
    duration_seconds: float
    fragments: tuple[VideoFragmentEvidence, ...]
    source_refs: tuple[str, ...]
    rights_refs: tuple[str, ...]
    simulated: bool

    @property
    def digest(self) -> str:
        return _digest(asdict(self))


@dataclass(frozen=True, slots=True)
class VideoFusionHit:
    timeline_id: str
    parent_record_id: str
    parent_record_digest: str
    parent_asset_digest: str
    timeline_digest: str
    score: float
    modality_scores: tuple[tuple[LearningModality, float], ...]
    fragments: tuple[VideoFragmentEvidence, ...]
    source_refs: tuple[str, ...]
    rights_refs: tuple[str, ...]
    instruction_trusted: bool = False

    def __post_init__(self) -> None:
        if self.instruction_trusted is not False:
            raise MultimodalFoundationError("video evidence never receives instruction authority")
        if (
            isinstance(self.score, bool)
            or not isinstance(self.score, (int, float))
            or not math.isfinite(self.score)
            or not 0 <= self.score <= 1
        ):
            raise MultimodalFoundationError("video fusion score must be finite in [0, 1]")


class VideoEvidenceIndex:
    """Bind verified declared video fragments and compute reproducible fusion.

    Parent container bytes and extraction offsets are explicit declarations.
    This index neither decodes containers nor claims embedding/model relevance.
    """

    def __init__(
        self,
        corpus: MultimodalCorpus,
        *,
        max_timelines: int = 128,
        max_fragments: int = 128,
        max_source_bytes: int = 134217728,
    ) -> None:
        if not isinstance(corpus, MultimodalCorpus):
            raise MultimodalFoundationError("video evidence requires the canonical corpus")
        self.corpus = corpus
        self.max_timelines = _integer("max_timelines", max_timelines, 128)
        self.max_fragments = _integer("max_fragments", max_fragments, 128)
        self.max_source_bytes = _integer("max_source_bytes", max_source_bytes, 134217728)
        self._timelines: dict[str, VideoTimelineReceipt] = {}
        self._digests: dict[str, str] = {}

    def _source_budget(self, record_ids: Sequence[str], prior: set[str] | None = None) -> set[str]:
        digests = set() if prior is None else set(prior)
        for rid in record_ids:
            record = self.corpus._records.get(rid)
            if record is None:
                raise MultimodalFoundationError("video source record is missing")
            if len(record.source_refs) > 128 or len(record.rights_refs) > 128:
                raise MultimodalFoundationError("video source provenance reference count exceeds ceiling")
            digests.add(record.asset_digest)
        sources = [self.corpus.store._objects.get(digest) for digest in digests]
        if any(not isinstance(payload, bytes) for payload in sources):
            raise MultimodalFoundationError("video source bytes are missing")
        if sum(len(payload) for payload in sources) > self.max_source_bytes:
            raise MultimodalFoundationError("video original source verification byte budget exceeded")
        return digests

    def bind(
        self, *, timeline_id: str, parent_record_id: str, fragments: Sequence[TimedMediaFragment]
    ) -> VideoTimelineReceipt:
        tid = _text("timeline_id", timeline_id, maximum=128)
        parent_id = _text("parent_record_id", parent_record_id)
        if (
            isinstance(fragments, (str, bytes))
            or not isinstance(fragments, Sequence)
            or not 1 <= len(fragments) <= self.max_fragments
        ):
            raise MultimodalFoundationError("video fragments require a bounded explicit ordered sequence")
        with self.corpus._lock:
            if any(not isinstance(fragment, TimedMediaFragment) for fragment in fragments):
                raise MultimodalFoundationError("video fragments require TimedMediaFragment")
            fragments = tuple(TimedMediaFragment(**asdict(fragment)) for fragment in fragments)
            self._source_budget((parent_id, *(fragment.record_id for fragment in fragments)))
            parent = self.corpus.get(parent_id)
            duration_ms = parent.metadata.get("duration_ms")
            if parent.modality is not LearningModality.VIDEO:
                raise MultimodalFoundationError("video timeline requires a VIDEO parent")
            duration = _integer("duration_ms", duration_ms, 3_600_000) / 1000
            seen_records: set[str] = set()
            seen_assets: set[str] = set()
            previous: dict[LearningModality, TimedMediaFragment] = {}
            evidence = []
            for fragment in fragments:
                if not isinstance(fragment, TimedMediaFragment):
                    raise MultimodalFoundationError("video fragments require TimedMediaFragment")
                fragment = TimedMediaFragment(**asdict(fragment))
                record = self.corpus.get(fragment.record_id)
                asset = self.corpus.intake._assets[record.record_id]
                if record.record_id in seen_records or record.asset_digest in seen_assets:
                    raise MultimodalFoundationError("duplicate video fragment identity")
                seen_records.add(record.record_id)
                seen_assets.add(record.asset_digest)
                if (
                    record.modality not in {LearningModality.IMAGE, LearningModality.AUDIO}
                    or not isinstance(asset, VerifiedMultimodalAsset)
                    or record.text_projection is None
                ):
                    raise MultimodalFoundationError(
                        "video fragments require verified image/audio text evidence"
                    )
                if (
                    parent.digest not in record.lineage_refs
                    or not set(parent.rights_refs).issubset(record.rights_refs)
                    or not set(parent.source_refs).issubset(record.source_refs)
                    or record.simulated != parent.simulated
                ):
                    raise MultimodalFoundationError(
                        "video fragment weakens parent provenance or simulation policy"
                    )
                if fragment.end_seconds > duration:
                    raise MultimodalFoundationError("video fragment exceeds parent duration")
                prior = previous.get(record.modality)
                if record.modality is LearningModality.IMAGE:
                    if fragment.source_frame_index is None or fragment.start_seconds != fragment.end_seconds:
                        raise MultimodalFoundationError(
                            "video images require point timestamps and source frame indices"
                        )
                    if fragment.start_seconds >= duration:
                        raise MultimodalFoundationError("video image lies outside parent duration")
                    if prior is not None and (
                        fragment.start_seconds <= prior.start_seconds
                        or fragment.source_frame_index <= prior.source_frame_index
                    ):
                        raise MultimodalFoundationError(
                            "video frame timestamps/indices must increase strictly"
                        )
                else:
                    if (
                        fragment.source_frame_index is not None
                        or fragment.start_seconds == fragment.end_seconds
                        or not math.isclose(
                            fragment.end_seconds - fragment.start_seconds,
                            asset.validation.duration_seconds,
                            rel_tol=0,
                            abs_tol=1e-9,
                        )
                    ):
                        raise MultimodalFoundationError("video audio span must match measured PCM duration")
                    if prior is not None and fragment.start_seconds < prior.end_seconds:
                        raise MultimodalFoundationError("video audio spans overlap or regress")
                previous[record.modality] = fragment
                evidence.append(
                    VideoFragmentEvidence(
                        fragment,
                        record.modality,
                        record.digest,
                        record.asset_digest,
                        record.text_projection.digest,
                        asset.validation.digest,
                        record.rights_refs,
                        record.source_refs,
                        record.lineage_refs,
                    )
                )
            receipt = VideoTimelineReceipt(
                tid,
                parent_id,
                parent.digest,
                parent.asset_digest,
                duration,
                tuple(evidence),
                parent.source_refs,
                parent.rights_refs,
                parent.simulated,
            )
            prior_receipt = self._timelines.get(tid)
            if prior_receipt is not None:
                self._verify(prior_receipt)
                if prior_receipt != receipt:
                    raise MultimodalFoundationError("video timeline identity conflict")
                return prior_receipt
            if len(self._timelines) >= self.max_timelines:
                raise MultimodalFoundationError("video timeline backpressure limit reached")
            self._timelines[tid], self._digests[tid] = receipt, receipt.digest
            return receipt

    def _verify(
        self, receipt: VideoTimelineReceipt, fragments: Sequence[VideoFragmentEvidence] | None = None
    ) -> None:
        if self._digests.get(receipt.timeline_id) != receipt.digest:
            raise MultimodalFoundationError("issued video timeline identity drift")
        parent = self.corpus.get(receipt.parent_record_id)
        if (
            parent.digest != receipt.parent_record_digest
            or parent.asset_digest != receipt.parent_asset_digest
        ):
            raise MultimodalFoundationError("video parent source identity drift")
        for evidence in receipt.fragments if fragments is None else fragments:
            record = self.corpus.get(evidence.fragment.record_id)
            asset = self.corpus.intake._assets[record.record_id]
            if (
                not isinstance(asset, VerifiedMultimodalAsset)
                or record.digest != evidence.record_digest
                or record.asset_digest != evidence.asset_digest
                or record.text_projection is None
                or record.text_projection.digest != evidence.projection_digest
                or asset.validation.digest != evidence.validation_digest
            ):
                raise MultimodalFoundationError("video fragment source/projection identity drift")

    def search(
        self,
        query: str,
        *,
        timeline_ids: Sequence[str],
        allowed_rights_refs: Sequence[str],
        weights: Mapping[LearningModality, int] | None = None,
        window_seconds: tuple[float, float] | None = None,
        include_simulated: bool = False,
        limit: int = 10,
    ) -> tuple[VideoFusionHit, ...]:
        q = _text("query", query, maximum=16384)
        selected = _bounded_refs("timeline_id", timeline_ids)
        if len(selected) > self.max_timelines:
            raise MultimodalFoundationError("video query scope exceeds timeline ceiling")
        allowed = set(_bounded_refs("allowed_rights_ref", allowed_rights_refs))
        if not isinstance(include_simulated, bool):
            raise MultimodalFoundationError("include_simulated must be boolean")
        count = _integer("limit", limit, 128)
        declared = {LearningModality.IMAGE: 2, LearningModality.AUDIO: 1} if weights is None else weights
        if (
            not isinstance(declared, Mapping)
            or not declared
            or len(declared) > 2
            or any(
                not isinstance(key, LearningModality)
                or key not in {LearningModality.IMAGE, LearningModality.AUDIO}
                for key in declared
            )
        ):
            raise MultimodalFoundationError("video fusion weights require explicit image/audio modalities")
        chosen = tuple(
            (modality, _integer("weight", declared[modality], 1000))
            for modality in (LearningModality.IMAGE, LearningModality.AUDIO)
            if modality in declared
        )
        window = None
        if window_seconds is not None:
            if not isinstance(window_seconds, tuple) or len(window_seconds) != 2:
                raise MultimodalFoundationError("video query window requires an explicit start/end tuple")
            window = tuple(_seconds("window_seconds", value) for value in window_seconds)
            if window[0] >= window[1]:
                raise MultimodalFoundationError("video query window is empty or reversed")
        query_tokens = {token.casefold() for token in _TOKEN.findall(q)}
        if not query_tokens:
            return ()
        with self.corpus._lock:
            hits = []
            source_digests: set[str] = set()
            for tid in selected:
                try:
                    receipt = self._timelines[tid]
                except KeyError as exc:
                    raise MultimodalFoundationError("video query references a missing timeline") from exc
                # Immutable issued policy fields fence scope before source reads/ranking.
                if self._digests.get(tid) != receipt.digest:
                    raise MultimodalFoundationError("issued video timeline identity drift")
                if (
                    receipt.simulated
                    and not include_simulated
                    or not set(receipt.rights_refs).issubset(allowed)
                ):
                    continue
                eligible = [
                    item
                    for item in receipt.fragments
                    if set(item.rights_refs).issubset(allowed)
                    and item.modality in declared
                    and (
                        window is None
                        or (
                            window[0] <= item.fragment.start_seconds < window[1]
                            if item.modality is LearningModality.IMAGE
                            else item.fragment.start_seconds < window[1]
                            and item.fragment.end_seconds > window[0]
                        )
                    )
                ]
                if not eligible:
                    continue
                source_digests = self._source_budget(
                    (receipt.parent_record_id, *(item.fragment.record_id for item in eligible)),
                    source_digests,
                )
                self._verify(receipt, eligible)
                scores = {modality: 0.0 for modality, _ in chosen}
                matched = []
                for evidence in eligible:
                    tokens = {
                        token.casefold()
                        for token in _TOKEN.findall(self.corpus._text[evidence.fragment.record_id])
                    }
                    overlap = query_tokens & tokens
                    if overlap:
                        score = len(overlap) / len(query_tokens | tokens)
                        scores[evidence.modality] = max(scores[evidence.modality], score)
                        matched.append(evidence)
                score = sum(scores[modality] * weight for modality, weight in chosen) / sum(
                    weight for _, weight in chosen
                )
                if score:
                    hits.append(
                        VideoFusionHit(
                            tid,
                            receipt.parent_record_id,
                            receipt.parent_record_digest,
                            receipt.parent_asset_digest,
                            receipt.digest,
                            score,
                            tuple((modality, scores[modality]) for modality, _ in chosen),
                            tuple(matched),
                            tuple(
                                dict.fromkeys(
                                    (
                                        *receipt.source_refs,
                                        *(ref for item in matched for ref in item.source_refs),
                                    )
                                )
                            ),
                            tuple(
                                dict.fromkeys(
                                    (
                                        *receipt.rights_refs,
                                        *(ref for item in matched for ref in item.rights_refs),
                                    )
                                )
                            ),
                        )
                    )
            return tuple(sorted(hits, key=lambda item: (-item.score, item.timeline_id))[:count])

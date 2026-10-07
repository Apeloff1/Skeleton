"""Integrated deterministic text-to-model-input pipeline.

Composes normalization, native tokenization, context-window preparation and
bounded batching without weakening the lower-level FLGB-02 contracts.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Iterable, Iterator, Sequence

from .flgb_model_runtime import TokenSequence, digest_json
from .text_normalization import normalize_text
from .tokenization import (
    NativeTokenizer, StreamingTextFeed, TokenBatch, TokenWindow,
    TokenizerContractError, batch_token_windows, iter_context_windows,
)


@dataclass(frozen=True)
class TextPipelineConfig:
    normalization: str = "NFC"
    context_size: int = 4096
    stride: int | None = None
    include_tail: bool = True
    max_batch_size: int = 32
    max_tokens_per_batch: int = 131072

    def __post_init__(self) -> None:
        if self.normalization not in {"NONE", "NFC", "NFD", "NFKC", "NFKD"}:
            raise TokenizerContractError("unsupported normalization")
        if isinstance(self.context_size, bool) or not isinstance(self.context_size, int) or self.context_size <= 0:
            raise TokenizerContractError("invalid context_size")
        if self.stride is not None and (
            isinstance(self.stride, bool) or not isinstance(self.stride, int)
            or self.stride <= 0 or self.stride > self.context_size
        ):
            raise TokenizerContractError("invalid stride")
        if isinstance(self.max_batch_size, bool) or not isinstance(self.max_batch_size, int) or self.max_batch_size <= 0:
            raise TokenizerContractError("invalid max_batch_size")
        if isinstance(self.max_tokens_per_batch, bool) or not isinstance(self.max_tokens_per_batch, int) or self.max_tokens_per_batch <= 0:
            raise TokenizerContractError("invalid max_tokens_per_batch")

    @property
    def digest(self) -> str:
        return digest_json({
            "normalization": self.normalization,
            "context_size": self.context_size,
            "stride": self.stride,
            "include_tail": self.include_tail,
            "max_batch_size": self.max_batch_size,
            "max_tokens_per_batch": self.max_tokens_per_batch,
        })


@dataclass(frozen=True)
class PreparedText:
    normalized_text: str
    sequence: TokenSequence
    windows: tuple[TokenWindow, ...]
    batches: tuple[TokenBatch, ...]
    pipeline_digest: str
    raw_text_digest: str
    normalized_text_digest: str

    def __post_init__(self) -> None:
        if len(self.pipeline_digest) != 64:
            raise TokenizerContractError("invalid pipeline digest")
        if len(self.raw_text_digest) != 64 or len(self.normalized_text_digest) != 64:
            raise TokenizerContractError("invalid text provenance digest")
        if any(ch not in "0123456789abcdef" for ch in self.raw_text_digest + self.normalized_text_digest):
            raise TokenizerContractError("text provenance digest must be lowercase hex")
        expected_normalized = sha256(self.normalized_text.encode("utf-8")).hexdigest()
        if self.normalized_text_digest != expected_normalized:
            raise TokenizerContractError("normalized text digest mismatch")
        if self.sequence.source_text_digest != self.normalized_text_digest:
            raise TokenizerContractError("sequence/normalized text provenance mismatch")
        if any(window.source_sequence_digest != self.sequence.digest for window in self.windows):
            raise TokenizerContractError("window provenance mismatch")
        flattened = tuple(window for batch in self.batches for window in batch.windows)
        if flattened != self.windows:
            raise TokenizerContractError("batch/window accounting mismatch")


@dataclass(frozen=True)
class TemporalTrainingSignal:
    """Leakage-safe year signal attached to a training source or example."""
    source_year: int
    observed_year: int
    knowledge_cutoff_year: int
    valid_from_year: int | None = None
    valid_to_year: int | None = None

    def __post_init__(self) -> None:
        years = (self.source_year, self.observed_year, self.knowledge_cutoff_year)
        if any(isinstance(year, bool) or not isinstance(year, int) or not 1000 <= year <= 9999 for year in years):
            raise TokenizerContractError("invalid temporal training year")
        for value in (self.valid_from_year, self.valid_to_year):
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or not 1000 <= value <= 9999):
                raise TokenizerContractError("invalid temporal validity year")
        if self.source_year > self.observed_year:
            raise TokenizerContractError("source year cannot be after observation year")
        if self.observed_year > self.knowledge_cutoff_year:
            raise TokenizerContractError("future observation exceeds knowledge cutoff")
        if self.valid_from_year is not None and self.valid_from_year > self.knowledge_cutoff_year:
            raise TokenizerContractError("future validity exceeds knowledge cutoff")
        if self.valid_from_year is not None and self.valid_to_year is not None and self.valid_to_year < self.valid_from_year:
            raise TokenizerContractError("invalid temporal validity interval")

    @property
    def age_years(self) -> int:
        return self.knowledge_cutoff_year - self.source_year

    @property
    def age_bucket(self) -> str:
        age = self.age_years
        if age == 0:
            return "current"
        if age <= 2:
            return "recent"
        if age <= 5:
            return "medium"
        if age <= 10:
            return "historical"
        return "archive"

    @property
    def digest(self) -> str:
        return digest_json({
            "source_year": self.source_year,
            "observed_year": self.observed_year,
            "knowledge_cutoff_year": self.knowledge_cutoff_year,
            "valid_from_year": self.valid_from_year,
            "valid_to_year": self.valid_to_year,
            "age_years": self.age_years,
            "age_bucket": self.age_bucket,
        })


@dataclass(frozen=True)
class DecadeTrainingSignal:
    """Coarse temporal feature derived from an exact leakage-safe year signal."""
    source_decade: int
    observed_decade: int
    cutoff_decade: int
    source_year: int
    cutoff_year: int

    def __post_init__(self) -> None:
        for value in (self.source_decade, self.observed_decade, self.cutoff_decade):
            if isinstance(value, bool) or not isinstance(value, int) or value % 10 or not 1000 <= value <= 9990:
                raise TokenizerContractError("invalid decade signal")
        if self.source_decade != (self.source_year // 10) * 10 or self.cutoff_decade != (self.cutoff_year // 10) * 10:
            raise TokenizerContractError("decade signal does not match exact year")
        if self.source_decade > self.observed_decade or self.observed_decade > self.cutoff_decade:
            raise TokenizerContractError("invalid decade chronology")

    @property
    def distance_decades(self) -> int:
        return (self.cutoff_decade - self.source_decade) // 10

    @property
    def cohort(self) -> str:
        distance = self.distance_decades
        if distance == 0:
            return "same-decade"
        if distance == 1:
            return "previous-decade"
        if distance <= 3:
            return "modern-history"
        if distance <= 7:
            return "long-history"
        return "deep-history"

    @property
    def digest(self) -> str:
        return digest_json(self.__dict__)


@dataclass(frozen=True)
class DecadeSignalVector:
    """Model-facing temporal feature vector derived without changing token identity."""
    source_decade: int
    cutoff_decade: int
    distance_decades: int
    recency_ppm: int
    chronology_digest: str

    def __post_init__(self) -> None:
        if self.source_decade % 10 or self.cutoff_decade % 10:
            raise TokenizerContractError("decade vector requires aligned decades")
        if self.distance_decades != (self.cutoff_decade - self.source_decade) // 10 or self.distance_decades < 0:
            raise TokenizerContractError("decade vector distance mismatch")
        if isinstance(self.recency_ppm, bool) or not isinstance(self.recency_ppm, int) or not 0 < self.recency_ppm <= 1_000_000:
            raise TokenizerContractError("invalid decade vector recency weight")
        if not isinstance(self.chronology_digest, str) or len(self.chronology_digest) != 64 or any(ch not in "0123456789abcdef" for ch in self.chronology_digest):
            raise TokenizerContractError("invalid decade vector chronology digest")

    @property
    def digest(self) -> str:
        return digest_json(self.__dict__)


def decade_weight_ppm(signal: DecadeTrainingSignal) -> int:
    if not isinstance(signal, DecadeTrainingSignal):
        raise TokenizerContractError("DecadeTrainingSignal required")
    distance = signal.distance_decades
    if distance == 0:
        return 1_000_000
    if distance == 1:
        return 800_000
    if distance <= 3:
        return 600_000
    if distance <= 7:
        return 350_000
    return 150_000


@dataclass(frozen=True)
class DecadeCorpusBucket:
    """Immutable accounting for one source decade in a prepared corpus."""
    decade: int
    document_ids: tuple[str, ...]
    token_count: int
    chronology_digests: tuple[str, ...]

    def __post_init__(self) -> None:
        if isinstance(self.decade, bool) or not isinstance(self.decade, int) or self.decade % 10 or not 1000 <= self.decade <= 9990:
            raise TokenizerContractError("invalid corpus decade")
        if not self.document_ids or len(self.document_ids) != len(self.chronology_digests):
            raise TokenizerContractError("invalid decade bucket membership")
        if len(set(self.document_ids)) != len(self.document_ids):
            raise TokenizerContractError("duplicate decade bucket document")
        if isinstance(self.token_count, bool) or not isinstance(self.token_count, int) or self.token_count <= 0:
            raise TokenizerContractError("invalid decade bucket token count")
        if any(not isinstance(v, str) or len(v) != 64 or any(ch not in "0123456789abcdef" for ch in v) for v in self.chronology_digests):
            raise TokenizerContractError("invalid decade bucket chronology digest")

    @property
    def digest(self) -> str:
        return digest_json({"decade": self.decade, "document_ids": list(self.document_ids), "token_count": self.token_count, "chronology_digests": list(self.chronology_digests)})


@dataclass(frozen=True)
class DecadeCoverageReceipt:
    """Deterministic temporal coverage evidence for a corpus."""
    pipeline_digest: str
    cutoff_year: int
    buckets: tuple[DecadeCorpusBucket, ...]
    document_count: int
    token_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.pipeline_digest, str) or len(self.pipeline_digest) != 64:
            raise TokenizerContractError("invalid decade coverage pipeline digest")
        if isinstance(self.cutoff_year, bool) or not isinstance(self.cutoff_year, int) or not 1000 <= self.cutoff_year <= 9999:
            raise TokenizerContractError("invalid decade coverage cutoff")
        if not self.buckets:
            raise TokenizerContractError("empty decade coverage")
        decades = tuple(bucket.decade for bucket in self.buckets)
        if decades != tuple(sorted(decades)) or len(set(decades)) != len(decades):
            raise TokenizerContractError("decade coverage buckets must be unique and ordered")
        if self.document_count != sum(len(bucket.document_ids) for bucket in self.buckets):
            raise TokenizerContractError("decade coverage document accounting mismatch")
        if self.token_count != sum(bucket.token_count for bucket in self.buckets):
            raise TokenizerContractError("decade coverage token accounting mismatch")

    @property
    def digest(self) -> str:
        return digest_json({"pipeline_digest": self.pipeline_digest, "cutoff_year": self.cutoff_year, "bucket_digests": [b.digest for b in self.buckets], "document_count": self.document_count, "token_count": self.token_count})


@dataclass(frozen=True)
class DecadeSamplingPlan:
    """Deterministic round-robin plan preventing a large decade from hiding others."""
    coverage_digest: str
    ordered_document_ids: tuple[str, ...]
    max_documents_per_decade: int

    def __post_init__(self) -> None:
        if not isinstance(self.coverage_digest, str) or len(self.coverage_digest) != 64:
            raise TokenizerContractError("invalid sampling coverage digest")
        if not self.ordered_document_ids or len(set(self.ordered_document_ids)) != len(self.ordered_document_ids):
            raise TokenizerContractError("invalid decade sampling document order")
        if isinstance(self.max_documents_per_decade, bool) or not isinstance(self.max_documents_per_decade, int) or self.max_documents_per_decade <= 0:
            raise TokenizerContractError("invalid decade sampling cap")

    @property
    def digest(self) -> str:
        return digest_json({"coverage_digest": self.coverage_digest, "ordered_document_ids": list(self.ordered_document_ids), "max_documents_per_decade": self.max_documents_per_decade})


@dataclass(frozen=True)
class TemporalRetrievalCandidate:
    """Candidate evidence with independent semantic and temporal relevance."""
    evidence_digest: str
    source_year: int
    valid_from_year: int | None
    valid_to_year: int | None
    semantic_score_ppm: int

    def __post_init__(self) -> None:
        if not isinstance(self.evidence_digest, str) or len(self.evidence_digest) != 64 or any(ch not in "0123456789abcdef" for ch in self.evidence_digest):
            raise TokenizerContractError("invalid temporal retrieval evidence digest")
        if isinstance(self.source_year, bool) or not isinstance(self.source_year, int) or not 1000 <= self.source_year <= 9999:
            raise TokenizerContractError("invalid retrieval source year")
        for value in (self.valid_from_year, self.valid_to_year):
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or not 1000 <= value <= 9999):
                raise TokenizerContractError("invalid retrieval validity year")
        if self.valid_from_year is not None and self.valid_to_year is not None and self.valid_to_year < self.valid_from_year:
            raise TokenizerContractError("invalid retrieval validity interval")
        if isinstance(self.semantic_score_ppm, bool) or not isinstance(self.semantic_score_ppm, int) or not 0 <= self.semantic_score_ppm <= 1_000_000:
            raise TokenizerContractError("invalid semantic relevance score")

    def temporally_valid(self, query_year: int) -> bool:
        if isinstance(query_year, bool) or not isinstance(query_year, int):
            raise TokenizerContractError("invalid temporal query year")
        if self.source_year > query_year:
            return False
        if self.valid_from_year is not None and query_year < self.valid_from_year:
            return False
        if self.valid_to_year is not None and query_year > self.valid_to_year:
            return False
        return True

    @property
    def digest(self) -> str:
        return digest_json(self.__dict__)


@dataclass(frozen=True)
class TemporalRetrievalPlan:
    query_year: int
    candidate_digests: tuple[str, ...]
    rejected_digests: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.candidate_digests:
            raise TokenizerContractError("temporal retrieval has no admissible evidence")
        if set(self.candidate_digests) & set(self.rejected_digests):
            raise TokenizerContractError("retrieval evidence cannot be admitted and rejected")

    @property
    def digest(self) -> str:
        return digest_json({"query_year": self.query_year, "candidate_digests": list(self.candidate_digests), "rejected_digests": list(self.rejected_digests)})


@dataclass(frozen=True)
class TemporalEvaluationSlice:
    """One cutoff-isolated evaluation slice; no example may exceed its horizon."""
    slice_id: str
    cutoff_year: int
    source_years: tuple[int, ...]
    example_digests: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.slice_id, str) or not self.slice_id or self.slice_id != self.slice_id.strip():
            raise TokenizerContractError("invalid temporal evaluation slice id")
        if isinstance(self.cutoff_year, bool) or not isinstance(self.cutoff_year, int) or not 1000 <= self.cutoff_year <= 9999:
            raise TokenizerContractError("invalid temporal evaluation cutoff")
        if not self.source_years or len(self.source_years) != len(self.example_digests):
            raise TokenizerContractError("invalid temporal evaluation membership")
        if any(isinstance(y, bool) or not isinstance(y, int) or y > self.cutoff_year for y in self.source_years):
            raise TokenizerContractError("temporal evaluation leaks beyond cutoff")
        if any(not isinstance(d, str) or len(d) != 64 or any(ch not in "0123456789abcdef" for ch in d) for d in self.example_digests):
            raise TokenizerContractError("invalid temporal evaluation digest")

    @property
    def digest(self) -> str:
        return digest_json({"slice_id": self.slice_id, "cutoff_year": self.cutoff_year, "source_years": list(self.source_years), "example_digests": list(self.example_digests)})


@dataclass(frozen=True)
class TemporalEvaluationResult:
    """Integer-only temporal metrics suitable for deterministic promotion gates."""
    slice_digest: str
    correct: int
    incorrect: int
    abstained: int
    inconsistent: int

    def __post_init__(self) -> None:
        if not isinstance(self.slice_digest, str) or len(self.slice_digest) != 64:
            raise TokenizerContractError("invalid temporal evaluation slice digest")
        values = (self.correct, self.incorrect, self.abstained, self.inconsistent)
        if any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in values) or sum(values) <= 0:
            raise TokenizerContractError("invalid temporal evaluation counts")

    @property
    def total(self) -> int:
        return self.correct + self.incorrect + self.abstained + self.inconsistent

    @property
    def accuracy_ppm(self) -> int:
        return self.correct * 1_000_000 // self.total

    @property
    def inconsistency_ppm(self) -> int:
        return self.inconsistent * 1_000_000 // self.total

    @property
    def digest(self) -> str:
        return digest_json({"slice_digest": self.slice_digest, "correct": self.correct, "incorrect": self.incorrect, "abstained": self.abstained, "inconsistent": self.inconsistent})


@dataclass(frozen=True)
class TemporalEvaluationGate:
    """Fail-closed acceptance criteria across independently scored time slices."""
    result_digests: tuple[str, ...]
    minimum_accuracy_ppm: int
    maximum_inconsistency_ppm: int
    passed: bool

    def __post_init__(self) -> None:
        if not self.result_digests or any(not isinstance(d, str) or len(d) != 64 for d in self.result_digests):
            raise TokenizerContractError("invalid temporal gate result digests")
        for value in (self.minimum_accuracy_ppm, self.maximum_inconsistency_ppm):
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 1_000_000:
                raise TokenizerContractError("invalid temporal gate threshold")

    @property
    def digest(self) -> str:
        return digest_json({"result_digests": list(self.result_digests), "minimum_accuracy_ppm": self.minimum_accuracy_ppm, "maximum_inconsistency_ppm": self.maximum_inconsistency_ppm, "passed": self.passed})


@dataclass(frozen=True)
class TemporalContradiction:
    """Explicit evidence that two time-scoped claims disagree."""
    left_signal_digest: str
    right_signal_digest: str
    left_source_year: int
    right_source_year: int
    cutoff_year: int
    resolution: str

    def __post_init__(self) -> None:
        for value in (self.left_signal_digest, self.right_signal_digest):
            if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
                raise TokenizerContractError("invalid contradiction signal digest")
        if self.left_signal_digest == self.right_signal_digest:
            raise TokenizerContractError("contradiction requires distinct signals")
        if self.resolution not in {"unresolved", "newer-wins", "coexists-by-validity"}:
            raise TokenizerContractError("invalid contradiction resolution")
        if max(self.left_source_year, self.right_source_year) > self.cutoff_year:
            raise TokenizerContractError("contradiction evidence exceeds cutoff")
        if self.resolution == "newer-wins" and self.left_source_year == self.right_source_year:
            raise TokenizerContractError("same-year contradiction cannot resolve by recency")

    @property
    def digest(self) -> str:
        return digest_json(self.__dict__)


@dataclass(frozen=True)
class TemporalSupersession:
    """Deterministic relationship between older and newer temporal evidence."""
    older_signal_digest: str
    newer_signal_digest: str
    older_source_year: int
    newer_source_year: int
    cutoff_year: int
    relation: str

    def __post_init__(self) -> None:
        for name in ("older_signal_digest", "newer_signal_digest"):
            value = getattr(self, name)
            if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
                raise TokenizerContractError(f"invalid {name}")
        if self.relation not in {"supersedes", "coexists"}:
            raise TokenizerContractError("invalid temporal relation")
        if self.newer_source_year < self.older_source_year:
            raise TokenizerContractError("temporal supersession runs backward")
        if self.newer_source_year > self.cutoff_year:
            raise TokenizerContractError("superseding evidence exceeds knowledge cutoff")
        if self.relation == "supersedes" and self.newer_source_year == self.older_source_year:
            raise TokenizerContractError("same-year evidence cannot supersede by year alone")

    @property
    def year_distance(self) -> int:
        return self.newer_source_year - self.older_source_year

    @property
    def digest(self) -> str:
        return digest_json(self.__dict__)


def temporal_weight_ppm(signal: TemporalTrainingSignal) -> int:
    """Deterministic recency prior in parts-per-million; never erases history."""
    if not isinstance(signal, TemporalTrainingSignal):
        raise TokenizerContractError("TemporalTrainingSignal required")
    age = signal.age_years
    if age == 0:
        return 1_000_000
    if age <= 2:
        return 850_000
    if age <= 5:
        return 650_000
    if age <= 10:
        return 400_000
    return 200_000


@dataclass(frozen=True)
class SupervisedTextExample:
    """One prompt/response example with a deterministic normalized boundary."""
    example_id: str
    prepared: PreparedText
    prompt_token_count: int
    prompt_digest: str
    response_digest: str
    temporal_signal_digest: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.example_id, str) or not self.example_id or self.example_id != self.example_id.strip():
            raise TokenizerContractError("invalid supervised example id")
        if not isinstance(self.prepared, PreparedText):
            raise TokenizerContractError("PreparedText required")
        if isinstance(self.prompt_token_count, bool) or not isinstance(self.prompt_token_count, int) or self.prompt_token_count <= 0:
            raise TokenizerContractError("invalid prompt token count")
        if self.prompt_token_count >= len(self.prepared.sequence.token_ids):
            raise TokenizerContractError("supervised example requires response tokens")
        for name in ("prompt_digest", "response_digest"):
            value = getattr(self, name)
            if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
                raise TokenizerContractError(f"invalid {name}")
        if self.temporal_signal_digest is not None and (not isinstance(self.temporal_signal_digest, str) or len(self.temporal_signal_digest) != 64 or any(ch not in "0123456789abcdef" for ch in self.temporal_signal_digest)):
            raise TokenizerContractError("invalid temporal signal digest")

    @property
    def digest(self) -> str:
        return digest_json({
            "example_id": self.example_id,
            "sequence_digest": self.prepared.sequence.digest,
            "prompt_token_count": self.prompt_token_count,
            "prompt_digest": self.prompt_digest,
            "response_digest": self.response_digest,
            "pipeline_digest": self.prepared.pipeline_digest,
            "temporal_signal_digest": self.temporal_signal_digest,
        })


@dataclass(frozen=True)
class ModelInputBatch:
    """Rectangular model-ready token ids with explicit attention semantics."""
    input_ids: tuple[tuple[int, ...], ...]
    attention_mask: tuple[tuple[int, ...], ...]
    position_ids: tuple[tuple[int, ...], ...]
    source_window_digests: tuple[str, ...]
    pad_token_id: int

    def __post_init__(self) -> None:
        if not self.input_ids:
            raise TokenizerContractError("empty model input batch")
        width = len(self.input_ids[0])
        if width <= 0 or any(len(row) != width for row in self.input_ids):
            raise TokenizerContractError("ragged model input ids")
        if len(self.attention_mask) != len(self.input_ids) or any(len(row) != width for row in self.attention_mask):
            raise TokenizerContractError("attention mask shape mismatch")
        if len(self.position_ids) != len(self.input_ids) or any(len(row) != width for row in self.position_ids):
            raise TokenizerContractError("position ids shape mismatch")
        if len(self.source_window_digests) != len(self.input_ids):
            raise TokenizerContractError("model batch provenance mismatch")
        if any(bit not in (0, 1) for row in self.attention_mask for bit in row):
            raise TokenizerContractError("invalid attention mask")
        for ids, mask, positions in zip(self.input_ids, self.attention_mask, self.position_ids):
            seen_padding = False
            expected_position = 0
            for token_id, bit, position in zip(ids, mask, positions):
                if isinstance(position, bool) or not isinstance(position, int) or position < 0:
                    raise TokenizerContractError("invalid position id")
                if position != (expected_position if bit else 0):
                    raise TokenizerContractError("position ids do not match attention mask")
                if bit:
                    expected_position += 1
                if bit == 0:
                    seen_padding = True
                    if token_id != self.pad_token_id:
                        raise TokenizerContractError("masked token is not padding")
                elif seen_padding:
                    raise TokenizerContractError("non-padding token after padding")

    @property
    def digest(self) -> str:
        return digest_json({"input_ids": [list(row) for row in self.input_ids], "attention_mask": [list(row) for row in self.attention_mask], "position_ids": [list(row) for row in self.position_ids], "source_window_digests": list(self.source_window_digests), "pad_token_id": self.pad_token_id})


def materialize_model_batch(windows: Sequence[TokenWindow], *, pad_token_id: int) -> ModelInputBatch:
    items = tuple(windows)
    if not items:
        raise TokenizerContractError("empty model input windows")
    if isinstance(pad_token_id, bool) or not isinstance(pad_token_id, int) or pad_token_id < 0:
        raise TokenizerContractError("invalid pad_token_id")
    if any(not isinstance(window, TokenWindow) for window in items):
        raise TokenizerContractError("TokenWindow required")
    width = max(len(window.token_ids) for window in items)
    rows, masks, positions, digests = [], [], [], []
    for window in items:
        padding = width - len(window.token_ids)
        rows.append(tuple(window.token_ids) + (pad_token_id,) * padding)
        masks.append((1,) * len(window.token_ids) + (0,) * padding)
        positions.append(tuple(range(len(window.token_ids))) + (0,) * padding)
        digests.append(window.digest)
    return ModelInputBatch(tuple(rows), tuple(masks), tuple(positions), tuple(digests), pad_token_id)


@dataclass(frozen=True)
class CausalTrainingBatch:
    """Next-token training tensors derived only from unmasked source tokens."""
    input_ids: tuple[tuple[int, ...], ...]
    labels: tuple[tuple[int, ...], ...]
    loss_mask: tuple[tuple[int, ...], ...]
    source_window_digests: tuple[str, ...]
    pad_token_id: int
    ignore_index: int = -100

    def __post_init__(self) -> None:
        if not self.input_ids:
            raise TokenizerContractError("empty causal training batch")
        width = len(self.input_ids[0])
        if width <= 0 or any(len(row) != width for row in self.input_ids):
            raise TokenizerContractError("ragged causal inputs")
        if len(self.labels) != len(self.input_ids) or any(len(row) != width for row in self.labels):
            raise TokenizerContractError("causal label shape mismatch")
        if len(self.loss_mask) != len(self.input_ids) or any(len(row) != width for row in self.loss_mask):
            raise TokenizerContractError("causal loss-mask shape mismatch")
        if len(self.source_window_digests) != len(self.input_ids):
            raise TokenizerContractError("causal provenance mismatch")
        if any(bit not in (0, 1) for row in self.loss_mask for bit in row):
            raise TokenizerContractError("invalid causal loss mask")
        for inputs, labels, mask in zip(self.input_ids, self.labels, self.loss_mask):
            for token_id in inputs:
                if isinstance(token_id, bool) or not isinstance(token_id, int) or token_id < 0:
                    raise TokenizerContractError("invalid causal input token")
            for label, bit in zip(labels, mask):
                if isinstance(label, bool) or not isinstance(label, int):
                    raise TokenizerContractError("invalid causal label")
                if (bit == 0) != (label == self.ignore_index):
                    raise TokenizerContractError("ignored labels/loss mask mismatch")
                if bit == 1 and label < 0:
                    raise TokenizerContractError("invalid active causal label")

    @property
    def digest(self) -> str:
        return digest_json({"input_ids": [list(row) for row in self.input_ids], "labels": [list(row) for row in self.labels], "loss_mask": [list(row) for row in self.loss_mask], "source_window_digests": list(self.source_window_digests), "pad_token_id": self.pad_token_id, "ignore_index": self.ignore_index})


MAX_SERIALIZED_BATCH_BYTES = 32_000_000


def _serialize_batch_payload(payload: dict) -> bytes:
    from .flgb_model_runtime import canonical_bytes
    value = canonical_bytes(payload)
    if len(value) > MAX_SERIALIZED_BATCH_BYTES:
        raise TokenizerContractError("serialized batch exceeds byte budget")
    return value


def serialize_model_input_batch(batch: ModelInputBatch) -> bytes:
    if not isinstance(batch, ModelInputBatch):
        raise TokenizerContractError("ModelInputBatch required")
    return _serialize_batch_payload({
        "schema": "skeleton.ai.model-input-batch.v1",
        "input_ids": [list(row) for row in batch.input_ids],
        "attention_mask": [list(row) for row in batch.attention_mask],
        "position_ids": [list(row) for row in batch.position_ids],
        "source_window_digests": list(batch.source_window_digests),
        "pad_token_id": batch.pad_token_id,
        "digest": batch.digest,
    })


def deserialize_model_input_batch(payload: bytes) -> ModelInputBatch:
    if not isinstance(payload, bytes) or len(payload) > MAX_SERIALIZED_BATCH_BYTES:
        raise TokenizerContractError("invalid serialized model batch bytes")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TokenizerContractError("invalid serialized model batch") from exc
    expected = {"schema", "input_ids", "attention_mask", "position_ids", "source_window_digests", "pad_token_id", "digest"}
    if not isinstance(value, dict) or set(value) != expected or value["schema"] != "skeleton.ai.model-input-batch.v1":
        raise TokenizerContractError("serialized model batch has invalid shape")
    batch = ModelInputBatch(
        tuple(tuple(row) for row in value["input_ids"]),
        tuple(tuple(row) for row in value["attention_mask"]),
        tuple(tuple(row) for row in value["position_ids"]),
        tuple(value["source_window_digests"]),
        value["pad_token_id"],
    )
    if value["digest"] != batch.digest:
        raise TokenizerContractError("serialized model batch digest mismatch")
    return batch


def serialize_causal_training_batch(batch: CausalTrainingBatch) -> bytes:
    if not isinstance(batch, CausalTrainingBatch):
        raise TokenizerContractError("CausalTrainingBatch required")
    return _serialize_batch_payload({
        "schema": "skeleton.ai.causal-training-batch.v1",
        "input_ids": [list(row) for row in batch.input_ids],
        "labels": [list(row) for row in batch.labels],
        "loss_mask": [list(row) for row in batch.loss_mask],
        "source_window_digests": list(batch.source_window_digests),
        "pad_token_id": batch.pad_token_id,
        "ignore_index": batch.ignore_index,
        "digest": batch.digest,
    })


def deserialize_causal_training_batch(payload: bytes) -> CausalTrainingBatch:
    if not isinstance(payload, bytes) or len(payload) > MAX_SERIALIZED_BATCH_BYTES:
        raise TokenizerContractError("invalid serialized causal batch bytes")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TokenizerContractError("invalid serialized causal batch") from exc
    expected = {"schema", "input_ids", "labels", "loss_mask", "source_window_digests", "pad_token_id", "ignore_index", "digest"}
    if not isinstance(value, dict) or set(value) != expected or value["schema"] != "skeleton.ai.causal-training-batch.v1":
        raise TokenizerContractError("serialized causal batch has invalid shape")
    batch = CausalTrainingBatch(
        tuple(tuple(row) for row in value["input_ids"]),
        tuple(tuple(row) for row in value["labels"]),
        tuple(tuple(row) for row in value["loss_mask"]),
        tuple(value["source_window_digests"]),
        value["pad_token_id"],
        value["ignore_index"],
    )
    if value["digest"] != batch.digest:
        raise TokenizerContractError("serialized causal batch digest mismatch")
    return batch


def materialize_causal_training_batch(batch: ModelInputBatch, *, ignore_index: int = -100) -> CausalTrainingBatch:
    if not isinstance(batch, ModelInputBatch):
        raise TokenizerContractError("ModelInputBatch required")
    if isinstance(ignore_index, bool) or not isinstance(ignore_index, int):
        raise TokenizerContractError("invalid ignore_index")
    inputs, labels, masks = [], [], []
    for row, attention in zip(batch.input_ids, batch.attention_mask):
        active = sum(attention)
        if active < 2:
            continue
        width = len(row) - 1
        source = tuple(row[:-1])
        target = tuple(row[1:])
        loss = tuple(1 if index < active - 1 else 0 for index in range(width))
        target = tuple(token if bit else ignore_index for token, bit in zip(target, loss))
        inputs.append(source)
        labels.append(target)
        masks.append(loss)
    if not inputs:
        raise TokenizerContractError("causal batch requires at least two source tokens")
    digests = tuple(d for d, row in zip(batch.source_window_digests, batch.attention_mask) if sum(row) >= 2)
    return CausalTrainingBatch(tuple(inputs), tuple(labels), tuple(masks), digests, batch.pad_token_id, ignore_index)


def mask_causal_prefix(batch: CausalTrainingBatch, prefix_lengths: Sequence[int]) -> CausalTrainingBatch:
    """Keep prompt tokens as context while supervising only response targets."""
    if not isinstance(batch, CausalTrainingBatch):
        raise TokenizerContractError("CausalTrainingBatch required")
    if len(prefix_lengths) != len(batch.input_ids):
        raise TokenizerContractError("prefix mask row count mismatch")
    labels, masks = [], []
    supervised = 0
    for row_labels, row_mask, prefix_length in zip(batch.labels, batch.loss_mask, prefix_lengths):
        if isinstance(prefix_length, bool) or not isinstance(prefix_length, int) or prefix_length < 0:
            raise TokenizerContractError("invalid prefix length")
        # label index i predicts source token i+1. A prefix of N source tokens
        # therefore masks target indices < N-1 while preserving response targets.
        cutoff = max(0, prefix_length - 1)
        next_mask = tuple(bit if index >= cutoff else 0 for index, bit in enumerate(row_mask))
        next_labels = tuple(label if bit else batch.ignore_index for label, bit in zip(row_labels, next_mask))
        labels.append(next_labels)
        masks.append(next_mask)
        supervised += sum(next_mask)
    if supervised <= 0:
        raise TokenizerContractError("prefix masking removed all supervised targets")
    return CausalTrainingBatch(batch.input_ids, tuple(labels), tuple(masks), batch.source_window_digests, batch.pad_token_id, batch.ignore_index)


@dataclass(frozen=True)
class TrainingInputReceipt:
    """Replayable identity for one prepared causal-training payload."""
    pipeline_digest: str
    tokenizer_digest: str
    sequence_digest: str
    batch_digests: tuple[str, ...]
    example_count: int
    supervised_token_count: int

    def __post_init__(self) -> None:
        for name in ("pipeline_digest", "tokenizer_digest", "sequence_digest"):
            value = getattr(self, name)
            if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
                raise TokenizerContractError(f"invalid {name}")
        if not self.batch_digests or any(not isinstance(d, str) or len(d) != 64 or any(ch not in "0123456789abcdef" for ch in d) for d in self.batch_digests):
            raise TokenizerContractError("invalid training batch digests")
        if isinstance(self.example_count, bool) or not isinstance(self.example_count, int) or self.example_count <= 0:
            raise TokenizerContractError("invalid training example count")
        if isinstance(self.supervised_token_count, bool) or not isinstance(self.supervised_token_count, int) or self.supervised_token_count <= 0:
            raise TokenizerContractError("invalid supervised token count")

    @property
    def digest(self) -> str:
        return digest_json({"pipeline_digest": self.pipeline_digest, "tokenizer_digest": self.tokenizer_digest, "sequence_digest": self.sequence_digest, "batch_digests": list(self.batch_digests), "example_count": self.example_count, "supervised_token_count": self.supervised_token_count})


@dataclass(frozen=True)
class GovernedTrainingInput:
    """Binds a replayable token payload to an admitted FLGB-07 dataset revision."""
    receipt_digest: str
    dataset_revision_digest: str
    transform_digest: str
    rights_digest: str
    authorized_scope: str

    def __post_init__(self) -> None:
        for name in ("receipt_digest", "dataset_revision_digest", "transform_digest", "rights_digest"):
            value = getattr(self, name)
            if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
                raise TokenizerContractError(f"invalid {name}")
        if not isinstance(self.authorized_scope, str) or not self.authorized_scope or self.authorized_scope != self.authorized_scope.strip() or any(ord(ch) < 32 for ch in self.authorized_scope):
            raise TokenizerContractError("invalid authorized_scope")

    @property
    def digest(self) -> str:
        return digest_json(self.__dict__)


@dataclass(frozen=True)
class PromotionAuthorizationRequest:
    """Non-authorizing handoff for an external production authority."""
    candidate_digest: str
    promotion_evidence_digest: str
    exact_head_commit: str
    requester: str

    def __post_init__(self) -> None:
        for name in ("candidate_digest", "promotion_evidence_digest", "exact_head_commit"):
            value = getattr(self, name)
            if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
                raise TokenizerContractError(f"invalid {name}")
        if not isinstance(self.requester, str) or not self.requester or self.requester != self.requester.strip():
            raise TokenizerContractError("invalid requester")

    @property
    def digest(self) -> str:
        return digest_json(self.__dict__)


@dataclass(frozen=True)
class PreparedCorpus:
    """Ordered, boundary-preserving collection of independently prepared documents."""
    documents: tuple[PreparedText, ...]
    document_ids: tuple[str, ...]
    pipeline_digest: str

    def __post_init__(self) -> None:
        if not self.documents or len(self.documents) != len(self.document_ids):
            raise TokenizerContractError("invalid prepared corpus")
        if len(set(self.document_ids)) != len(self.document_ids):
            raise TokenizerContractError("duplicate document id")
        if any(not isinstance(value, str) or not value or value != value.strip() for value in self.document_ids):
            raise TokenizerContractError("invalid document id")
        if any(document.pipeline_digest != self.pipeline_digest for document in self.documents):
            raise TokenizerContractError("mixed pipeline corpus")

    @property
    def digest(self) -> str:
        return digest_json({"document_ids": list(self.document_ids), "sequence_digests": [document.sequence.digest for document in self.documents], "raw_text_digests": [document.raw_text_digest for document in self.documents], "pipeline_digest": self.pipeline_digest})


@dataclass(frozen=True)
class CorpusTrainingReceipt:
    """Ordered training identity that preserves every document boundary."""
    pipeline_digest: str
    corpus_digest: str
    document_ids: tuple[str, ...]
    document_receipt_digests: tuple[str, ...]
    example_count: int
    supervised_token_count: int

    def __post_init__(self) -> None:
        for name in ("pipeline_digest", "corpus_digest"):
            value = getattr(self, name)
            if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
                raise TokenizerContractError(f"invalid {name}")
        if not self.document_ids or len(self.document_ids) != len(self.document_receipt_digests):
            raise TokenizerContractError("invalid corpus training documents")
        if len(set(self.document_ids)) != len(self.document_ids):
            raise TokenizerContractError("duplicate corpus training document id")
        if any(not isinstance(value, str) or not value or value != value.strip() for value in self.document_ids):
            raise TokenizerContractError("invalid corpus training document id")
        if any(not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value) for value in self.document_receipt_digests):
            raise TokenizerContractError("invalid document training receipt digest")
        if isinstance(self.example_count, bool) or not isinstance(self.example_count, int) or self.example_count <= 0:
            raise TokenizerContractError("invalid corpus example count")
        if isinstance(self.supervised_token_count, bool) or not isinstance(self.supervised_token_count, int) or self.supervised_token_count <= 0:
            raise TokenizerContractError("invalid corpus supervised token count")

    @property
    def digest(self) -> str:
        return digest_json({
            "pipeline_digest": self.pipeline_digest,
            "corpus_digest": self.corpus_digest,
            "document_ids": list(self.document_ids),
            "document_receipt_digests": list(self.document_receipt_digests),
            "example_count": self.example_count,
            "supervised_token_count": self.supervised_token_count,
        })


@dataclass(frozen=True)
class PipelineReplayCheckpoint:
    """Durable identity checkpoint for deterministic text/corpus replay."""
    pipeline_digest: str
    tokenizer_digest: str
    payload_digest: str
    payload_kind: str

    def __post_init__(self) -> None:
        for name in ("pipeline_digest", "tokenizer_digest", "payload_digest"):
            value = getattr(self, name)
            if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
                raise TokenizerContractError(f"invalid {name}")
        if self.payload_kind not in {"prepared-text", "prepared-corpus"}:
            raise TokenizerContractError("invalid replay payload kind")

    @property
    def digest(self) -> str:
        return digest_json(self.__dict__)


class TextTokenPipeline:
    """One admitted, immutable text-to-model-input pipeline."""

    SCHEMA = "skeleton.ai.text-token-pipeline.v1"

    def __init__(self, tokenizer: NativeTokenizer, config: TextPipelineConfig | None = None) -> None:
        if not isinstance(tokenizer, NativeTokenizer):
            raise TokenizerContractError("NativeTokenizer required")
        self.tokenizer = tokenizer
        self.config = config or TextPipelineConfig()
        self._digest = digest_json({
            "schema": self.SCHEMA,
            "tokenizer_digest": tokenizer.digest,
            "config_digest": self.config.digest,
        })

    @property
    def digest(self) -> str:
        return self._digest

    def normalize(self, text: str) -> str:
        value = normalize_text(text, self.config.normalization)
        if len(value) > self.tokenizer.limits.max_chars:
            raise TokenizerContractError("normalized text character budget exceeded")
        return value

    def encode(self, text: str) -> TokenSequence:
        self.tokenizer.assert_unchanged()
        return self.tokenizer.encode_sequence(self.normalize(text))

    def prepare(self, text: str) -> PreparedText:
        normalized = self.normalize(text)
        self.tokenizer.assert_unchanged()
        sequence = self.tokenizer.encode_sequence(normalized)
        windows = tuple(iter_context_windows(
            sequence,
            context_size=self.config.context_size,
            stride=self.config.stride,
            include_tail=self.config.include_tail,
        ))
        batches = batch_token_windows(
            windows,
            max_batch_size=self.config.max_batch_size,
            max_tokens_per_batch=self.config.max_tokens_per_batch,
        ) if windows else ()
        return PreparedText(
            normalized,
            sequence,
            windows,
            batches,
            self.digest,
            sha256(text.encode("utf-8")).hexdigest(),
            sha256(normalized.encode("utf-8")).hexdigest(),
        )

    def temporal_signal(self, *, source_year: int, observed_year: int, knowledge_cutoff_year: int, valid_from_year: int | None = None, valid_to_year: int | None = None) -> TemporalTrainingSignal:
        return TemporalTrainingSignal(source_year, observed_year, knowledge_cutoff_year, valid_from_year, valid_to_year)

    def decade_signal(self, signal: TemporalTrainingSignal) -> DecadeTrainingSignal:
        if not isinstance(signal, TemporalTrainingSignal):
            raise TokenizerContractError("TemporalTrainingSignal required")
        return DecadeTrainingSignal(
            (signal.source_year // 10) * 10,
            (signal.observed_year // 10) * 10,
            (signal.knowledge_cutoff_year // 10) * 10,
            signal.source_year,
            signal.knowledge_cutoff_year,
        )

    def decade_signal_vector(self, signal: TemporalTrainingSignal) -> DecadeSignalVector:
        """Derive a bounded decade feature while preserving exact-year provenance."""
        decade = self.decade_signal(signal)
        return DecadeSignalVector(
            source_decade=decade.source_decade,
            cutoff_decade=decade.cutoff_decade,
            distance_decades=decade.distance_decades,
            recency_ppm=decade_weight_ppm(decade),
            chronology_digest=signal.digest,
        )

    def decade_coverage(self, corpus: PreparedCorpus, signals: Sequence[TemporalTrainingSignal]) -> DecadeCoverageReceipt:
        if not isinstance(corpus, PreparedCorpus) or corpus.pipeline_digest != self.digest:
            raise TokenizerContractError("corpus belongs to another pipeline")
        items = tuple(signals)
        if len(items) != len(corpus.documents) or any(not isinstance(s, TemporalTrainingSignal) for s in items):
            raise TokenizerContractError("one temporal signal required per corpus document")
        cutoffs = {s.knowledge_cutoff_year for s in items}
        if len(cutoffs) != 1:
            raise TokenizerContractError("corpus temporal signals use different knowledge cutoffs")
        grouped: dict[int, list[tuple[str, PreparedText, TemporalTrainingSignal]]] = {}
        for document_id, document, signal in zip(corpus.document_ids, corpus.documents, items):
            decade = (signal.source_year // 10) * 10
            grouped.setdefault(decade, []).append((document_id, document, signal))
        buckets = tuple(
            DecadeCorpusBucket(
                decade,
                tuple(item[0] for item in grouped[decade]),
                sum(len(item[1].sequence.token_ids) for item in grouped[decade]),
                tuple(item[2].digest for item in grouped[decade]),
            )
            for decade in sorted(grouped)
        )
        return DecadeCoverageReceipt(self.digest, next(iter(cutoffs)), buckets, len(corpus.documents), sum(len(d.sequence.token_ids) for d in corpus.documents))

    def decade_sampling_plan(self, coverage: DecadeCoverageReceipt, *, max_documents_per_decade: int) -> DecadeSamplingPlan:
        if not isinstance(coverage, DecadeCoverageReceipt) or coverage.pipeline_digest != self.digest:
            raise TokenizerContractError("decade coverage belongs to another pipeline")
        if isinstance(max_documents_per_decade, bool) or not isinstance(max_documents_per_decade, int) or max_documents_per_decade <= 0:
            raise TokenizerContractError("invalid decade sampling cap")
        buckets = [bucket.document_ids[:max_documents_per_decade] for bucket in coverage.buckets]
        ordered = []
        for index in range(max((len(ids) for ids in buckets), default=0)):
            for ids in buckets:
                if index < len(ids):
                    ordered.append(ids[index])
        if not ordered:
            raise TokenizerContractError("decade sampling produced no documents")
        return DecadeSamplingPlan(coverage.digest, tuple(ordered), max_documents_per_decade)

    def temporal_retrieval_plan(self, candidates: Sequence[TemporalRetrievalCandidate], *, query_year: int, limit: int = 8) -> TemporalRetrievalPlan:
        items = tuple(candidates)
        if not items or any(not isinstance(item, TemporalRetrievalCandidate) for item in items):
            raise TokenizerContractError("temporal retrieval candidates required")
        if isinstance(query_year, bool) or not isinstance(query_year, int) or not 1000 <= query_year <= 9999:
            raise TokenizerContractError("invalid temporal query year")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise TokenizerContractError("invalid temporal retrieval limit")
        admitted = [item for item in items if item.temporally_valid(query_year)]
        rejected = [item for item in items if not item.temporally_valid(query_year)]
        admitted.sort(key=lambda item: (-item.semantic_score_ppm, -item.source_year, item.evidence_digest))
        selected = admitted[:limit]
        if not selected:
            raise TokenizerContractError("no temporally admissible retrieval evidence")
        return TemporalRetrievalPlan(query_year, tuple(item.digest for item in selected), tuple(item.digest for item in rejected))

    def temporal_evaluation_slice(self, slice_id: str, signals: Sequence[TemporalTrainingSignal], example_digests: Sequence[str], *, cutoff_year: int) -> TemporalEvaluationSlice:
        items = tuple(signals)
        digests = tuple(example_digests)
        if len(items) != len(digests) or any(not isinstance(s, TemporalTrainingSignal) for s in items):
            raise TokenizerContractError("one temporal signal required per evaluation example")
        if any(s.knowledge_cutoff_year > cutoff_year or s.observed_year > cutoff_year or s.source_year > cutoff_year for s in items):
            raise TokenizerContractError("evaluation signal exceeds historical cutoff")
        return TemporalEvaluationSlice(slice_id, cutoff_year, tuple(s.source_year for s in items), digests)

    def temporal_evaluation_gate(self, results: Sequence[TemporalEvaluationResult], *, minimum_accuracy_ppm: int, maximum_inconsistency_ppm: int) -> TemporalEvaluationGate:
        items = tuple(results)
        if not items or any(not isinstance(r, TemporalEvaluationResult) for r in items):
            raise TokenizerContractError("temporal evaluation results required")
        if isinstance(minimum_accuracy_ppm, bool) or not isinstance(minimum_accuracy_ppm, int) or not 0 <= minimum_accuracy_ppm <= 1_000_000:
            raise TokenizerContractError("invalid minimum temporal accuracy")
        if isinstance(maximum_inconsistency_ppm, bool) or not isinstance(maximum_inconsistency_ppm, int) or not 0 <= maximum_inconsistency_ppm <= 1_000_000:
            raise TokenizerContractError("invalid maximum temporal inconsistency")
        passed = all(r.accuracy_ppm >= minimum_accuracy_ppm and r.inconsistency_ppm <= maximum_inconsistency_ppm for r in items)
        return TemporalEvaluationGate(tuple(r.digest for r in items), minimum_accuracy_ppm, maximum_inconsistency_ppm, passed)

    def temporal_contradiction(self, left: TemporalTrainingSignal, right: TemporalTrainingSignal, *, resolution: str = "unresolved") -> TemporalContradiction:
        if not isinstance(left, TemporalTrainingSignal) or not isinstance(right, TemporalTrainingSignal):
            raise TokenizerContractError("temporal signals required")
        if left.knowledge_cutoff_year != right.knowledge_cutoff_year:
            raise TokenizerContractError("temporal signals use different knowledge cutoffs")
        return TemporalContradiction(left.digest, right.digest, left.source_year, right.source_year, left.knowledge_cutoff_year, resolution)

    def temporal_supersession(self, older: TemporalTrainingSignal, newer: TemporalTrainingSignal, *, supersedes: bool) -> TemporalSupersession:
        if not isinstance(older, TemporalTrainingSignal) or not isinstance(newer, TemporalTrainingSignal):
            raise TokenizerContractError("temporal signals required")
        if older.knowledge_cutoff_year != newer.knowledge_cutoff_year:
            raise TokenizerContractError("temporal signals use different knowledge cutoffs")
        return TemporalSupersession(
            older.digest, newer.digest, older.source_year, newer.source_year,
            older.knowledge_cutoff_year, "supersedes" if supersedes else "coexists",
        )

    def prepare_supervised_example(self, example_id: str, prompt: str, response: str, *, temporal_signal: TemporalTrainingSignal | None = None) -> SupervisedTextExample:
        if not isinstance(prompt, str) or not isinstance(response, str) or not prompt or not response:
            raise TokenizerContractError("supervised prompt and response required")
        normalized_prompt = self.normalize(prompt)
        normalized_response = self.normalize(response)
        prompt_sequence = self.tokenizer.encode_sequence(normalized_prompt)
        prepared = self.prepare(prompt + response)
        prompt_count = len(prompt_sequence.token_ids)
        if tuple(prepared.sequence.token_ids[:prompt_count]) != tuple(prompt_sequence.token_ids):
            raise TokenizerContractError("tokenizer is not prefix-stable across prompt/response boundary")
        return SupervisedTextExample(
            example_id,
            prepared,
            prompt_count,
            sha256(normalized_prompt.encode("utf-8")).hexdigest(),
            sha256(normalized_response.encode("utf-8")).hexdigest(),
            temporal_signal.digest if temporal_signal is not None else None,
        )

    def supervised_training_batches(self, example: SupervisedTextExample, *, pad_token_id: int | None = None, ignore_index: int = -100) -> tuple[CausalTrainingBatch, ...]:
        if not isinstance(example, SupervisedTextExample) or example.prepared.pipeline_digest != self.digest:
            raise TokenizerContractError("supervised example belongs to another pipeline")
        batches = self.causal_training_batches(example.prepared, pad_token_id=pad_token_id, ignore_index=ignore_index)
        output, consumed = [], 0
        for batch in batches:
            prefix_lengths = []
            for mask in batch.loss_mask:
                row_source_tokens = len(mask) + 1
                remaining_prompt = max(0, example.prompt_token_count - consumed)
                prefix_lengths.append(min(row_source_tokens, remaining_prompt))
                consumed += row_source_tokens
            if any(any(bit and index >= max(0, prefix - 1) for index, bit in enumerate(mask)) for mask, prefix in zip(batch.loss_mask, prefix_lengths)):
                output.append(mask_causal_prefix(batch, tuple(prefix_lengths)))
        if not output:
            raise TokenizerContractError("supervised example produced no response targets")
        return tuple(output)

    def prepare_corpus(self, documents: Iterable[tuple[str, str]]) -> PreparedCorpus:
        prepared, document_ids = [], []
        for document_id, text in documents:
            if not isinstance(document_id, str) or not isinstance(text, str):
                raise TokenizerContractError("corpus entries require string id and text")
            document_ids.append(document_id)
            prepared.append(self.prepare(text))
        return PreparedCorpus(tuple(prepared), tuple(document_ids), self.digest)

    def corpus_training_receipts(self, corpus: PreparedCorpus, *, pad_token_id: int | None = None, ignore_index: int = -100) -> tuple[TrainingInputReceipt, ...]:
        if not isinstance(corpus, PreparedCorpus) or corpus.pipeline_digest != self.digest:
            raise TokenizerContractError("corpus belongs to another pipeline")
        return tuple(self.training_receipt(document, pad_token_id=pad_token_id, ignore_index=ignore_index) for document in corpus.documents)

    def corpus_training_receipt(self, corpus: PreparedCorpus, *, pad_token_id: int | None = None, ignore_index: int = -100) -> CorpusTrainingReceipt:
        receipts = self.corpus_training_receipts(corpus, pad_token_id=pad_token_id, ignore_index=ignore_index)
        return CorpusTrainingReceipt(
            self.digest,
            corpus.digest,
            corpus.document_ids,
            tuple(receipt.digest for receipt in receipts),
            sum(receipt.example_count for receipt in receipts),
            sum(receipt.supervised_token_count for receipt in receipts),
        )

    def verify_corpus_training_receipt(self, corpus: PreparedCorpus, receipt: CorpusTrainingReceipt, *, pad_token_id: int | None = None, ignore_index: int = -100) -> bool:
        if not isinstance(receipt, CorpusTrainingReceipt):
            raise TokenizerContractError("CorpusTrainingReceipt required")
        expected = self.corpus_training_receipt(corpus, pad_token_id=pad_token_id, ignore_index=ignore_index)
        if expected.digest != receipt.digest:
            raise TokenizerContractError("corpus training receipt mismatch")
        return True

    def replay_checkpoint(self, payload: PreparedText | PreparedCorpus) -> PipelineReplayCheckpoint:
        if isinstance(payload, PreparedText):
            if payload.pipeline_digest != self.digest:
                raise TokenizerContractError("prepared text belongs to another pipeline")
            payload_digest, kind = payload.sequence.digest, "prepared-text"
        elif isinstance(payload, PreparedCorpus):
            if payload.pipeline_digest != self.digest:
                raise TokenizerContractError("corpus belongs to another pipeline")
            payload_digest, kind = payload.digest, "prepared-corpus"
        else:
            raise TokenizerContractError("prepared payload required")
        return PipelineReplayCheckpoint(self.digest, self.tokenizer.digest, payload_digest, kind)

    def verify_replay_checkpoint(self, payload: PreparedText | PreparedCorpus, checkpoint: PipelineReplayCheckpoint) -> None:
        if not isinstance(checkpoint, PipelineReplayCheckpoint):
            raise TokenizerContractError("PipelineReplayCheckpoint required")
        if self.replay_checkpoint(payload).digest != checkpoint.digest:
            raise TokenizerContractError("pipeline replay checkpoint mismatch")

    def model_batches(self, prepared: PreparedText, *, pad_token_id: int | None = None) -> tuple[ModelInputBatch, ...]:
        if not isinstance(prepared, PreparedText) or prepared.pipeline_digest != self.digest:
            raise TokenizerContractError("prepared text belongs to another pipeline")
        if pad_token_id is None:
            pad = self.tokenizer.special_token_id("pad")
            if pad is None:
                raise TokenizerContractError("tokenizer does not declare pad token; explicit pad_token_id required")
        else:
            pad = pad_token_id
        if isinstance(pad, bool) or not isinstance(pad, int) or not 0 <= pad < self.tokenizer.vocab_size:
            raise TokenizerContractError("padding token outside vocabulary")
        return tuple(materialize_model_batch(batch.windows, pad_token_id=pad) for batch in prepared.batches)

    def causal_training_batches(self, prepared: PreparedText, *, pad_token_id: int | None = None, ignore_index: int = -100) -> tuple[CausalTrainingBatch, ...]:
        batches = self.model_batches(prepared, pad_token_id=pad_token_id)
        output = []
        for batch in batches:
            if not any(sum(row) >= 2 for row in batch.attention_mask):
                continue
            output.append(materialize_causal_training_batch(batch, ignore_index=ignore_index))
        return tuple(output)

    def training_receipt(self, prepared: PreparedText, *, pad_token_id: int | None = None, ignore_index: int = -100) -> TrainingInputReceipt:
        batches = self.causal_training_batches(prepared, pad_token_id=pad_token_id, ignore_index=ignore_index)
        if not batches:
            raise TokenizerContractError("no trainable causal examples")
        return TrainingInputReceipt(
            self.digest,
            self.tokenizer.digest,
            prepared.sequence.digest,
            tuple(batch.digest for batch in batches),
            sum(len(batch.input_ids) for batch in batches),
            sum(sum(row) for batch in batches for row in batch.loss_mask),
        )

    def verify_training_receipt(self, prepared: PreparedText, receipt: TrainingInputReceipt, *, pad_token_id: int | None = None, ignore_index: int = -100) -> None:
        if not isinstance(receipt, TrainingInputReceipt):
            raise TokenizerContractError("TrainingInputReceipt required")
        expected = self.training_receipt(prepared, pad_token_id=pad_token_id, ignore_index=ignore_index)
        if expected.digest != receipt.digest:
            raise TokenizerContractError("training input receipt mismatch")

    def governed_training_input(self, prepared: PreparedText, dataset_revision, dataset_rights, *, scope: str = "training", pad_token_id: int | None = None, ignore_index: int = -100) -> GovernedTrainingInput:
        from skeleton.ai.training.flgb_training_runtime import DatasetRevision, DatasetRights
        if not isinstance(dataset_revision, DatasetRevision):
            raise TokenizerContractError("DatasetRevision required")
        if not isinstance(dataset_rights, DatasetRights):
            raise TokenizerContractError("DatasetRights required")
        if dataset_rights.dataset_id != dataset_revision.dataset_id:
            raise TokenizerContractError("dataset rights identity mismatch")
        if dataset_rights.digest != dataset_revision.rights_digest:
            raise TokenizerContractError("dataset rights digest mismatch")
        if not dataset_rights.permits(scope):
            raise TokenizerContractError("dataset rights do not permit requested training scope")
        receipt = self.training_receipt(prepared, pad_token_id=pad_token_id, ignore_index=ignore_index)
        if dataset_revision.content_digest != prepared.raw_text_digest:
            raise TokenizerContractError("dataset content does not match prepared source")
        if dataset_revision.transform_digest != self.digest:
            raise TokenizerContractError("dataset transform does not match pipeline")
        return GovernedTrainingInput(receipt.digest, dataset_revision.digest, dataset_revision.transform_digest, dataset_rights.digest, scope)

    def training_manifest(self, prepared: PreparedText, dataset_revision, dataset_rights, *, scope: str = "training", run_id: str, base_model_digest: str, code_digest: str, seed_manifest_digest: str, max_steps: int, pad_token_id: int | None = None, ignore_index: int = -100):
        from skeleton.ai.training.flgb_training_runtime import TrainingManifest
        governed = self.governed_training_input(prepared, dataset_revision, dataset_rights, scope=scope, pad_token_id=pad_token_id, ignore_index=ignore_index)
        return TrainingManifest(
            run_id=run_id,
            base_model_digest=base_model_digest,
            dataset_revision_digests=(governed.dataset_revision_digest,),
            code_digest=code_digest,
            config_digest=digest_json({"pipeline_digest": self.digest, "training_input_digest": governed.digest}),
            seed_manifest_digest=seed_manifest_digest,
            max_steps=max_steps,
        )

    def initial_training_checkpoint(self, manifest, *, weights_digest: str, optimizer_digest: str, rng_digest: str):
        from skeleton.ai.training.flgb_training_runtime import TrainingCheckpoint, TrainingManifest
        if not isinstance(manifest, TrainingManifest):
            raise TokenizerContractError("TrainingManifest required")
        return TrainingCheckpoint(
            run_manifest_digest=manifest.digest,
            sequence=0,
            weights_digest=weights_digest,
            optimizer_digest=optimizer_digest,
            rng_digest=rng_digest,
        )

    def candidate_from_checkpoint(self, manifest, checkpoint, *, candidate_id: str, base_model_digest: str):
        from skeleton.ai.training.flgb_training_runtime import CandidateWeights, TrainingCheckpoint, TrainingManifest
        if not isinstance(manifest, TrainingManifest) or not isinstance(checkpoint, TrainingCheckpoint):
            raise TokenizerContractError("training manifest/checkpoint required")
        if checkpoint.run_manifest_digest != manifest.digest:
            raise TokenizerContractError("checkpoint does not belong to training manifest")
        if manifest.base_model_digest != base_model_digest:
            raise TokenizerContractError("candidate base model mismatch")
        return CandidateWeights(
            candidate_id=candidate_id,
            weights_digest=checkpoint.weights_digest,
            training_lineage_digest=checkpoint.digest,
            base_model_digest=base_model_digest,
        )

    def advance_training_checkpoint(self, manifest, checkpoint, *, weights_digest: str, optimizer_digest: str, rng_digest: str):
        from skeleton.ai.training.flgb_training_runtime import TrainingCheckpoint, TrainingManifest
        if not isinstance(manifest, TrainingManifest) or not isinstance(checkpoint, TrainingCheckpoint):
            raise TokenizerContractError("training manifest/checkpoint required")
        if checkpoint.run_manifest_digest != manifest.digest:
            raise TokenizerContractError("checkpoint does not belong to training manifest")
        return checkpoint.next(weights_digest, optimizer_digest, rng_digest)

    def mirror_evaluation(self, candidate, *, evaluation_id: str, champion_digest: str, candidate_score_ppm: int, champion_score_ppm: int, risk_gate_passed: bool, independent_verifier: str, evidence_digest: str):
        from skeleton.ai.training.flgb_training_runtime import CandidateWeights, MirrorEvaluation
        if not isinstance(candidate, CandidateWeights):
            raise TokenizerContractError("CandidateWeights required")
        if candidate.status != "candidate":
            raise TokenizerContractError("only candidate weights may enter mirror evaluation")
        return MirrorEvaluation(
            evaluation_id=evaluation_id,
            candidate_digest=candidate.digest,
            champion_digest=champion_digest,
            candidate_score_ppm=candidate_score_ppm,
            champion_score_ppm=champion_score_ppm,
            risk_gate_passed=risk_gate_passed,
            independent_verifier=independent_verifier,
            evidence_digest=evidence_digest,
        )

    def promotion_evidence(self, candidate, evaluation, *, exact_head_commit: str, rights_digest: str, contamination_scan_digest: str, rollback_digest: str, independent_verifier: str, rights_passed: bool, contamination_clear: bool, rollback_ready: bool):
        from skeleton.ai.training.flgb_training_runtime import CandidateWeights, MirrorEvaluation, PromotionEvidence
        if not isinstance(candidate, CandidateWeights) or not isinstance(evaluation, MirrorEvaluation):
            raise TokenizerContractError("candidate/evaluation required")
        if candidate.status != "candidate":
            raise TokenizerContractError("only candidate weights may produce promotion evidence")
        if evaluation.candidate_digest != candidate.digest:
            raise TokenizerContractError("evaluation does not belong to candidate")
        if not isinstance(rights_passed, bool) or not isinstance(contamination_clear, bool) or not isinstance(rollback_ready, bool):
            raise TokenizerContractError("promotion gate flags must be boolean")
        if evaluation.independent_verifier == independent_verifier:
            raise TokenizerContractError("promotion requires verifier separation")
        return PromotionEvidence(
            candidate_digest=candidate.digest,
            exact_head_commit=exact_head_commit,
            rights_digest=rights_digest,
            contamination_scan_digest=contamination_scan_digest,
            evaluation_digest=digest_json({
                "evaluation_id": evaluation.evaluation_id,
                "candidate_digest": evaluation.candidate_digest,
                "champion_digest": evaluation.champion_digest,
                "candidate_score_ppm": evaluation.candidate_score_ppm,
                "champion_score_ppm": evaluation.champion_score_ppm,
                "risk_gate_passed": evaluation.risk_gate_passed,
                "independent_verifier": evaluation.independent_verifier,
                "evidence_digest": evaluation.evidence_digest,
            }),
            rollback_digest=rollback_digest,
            independent_verifier=independent_verifier,
            rights_passed=rights_passed,
            contamination_clear=contamination_clear,
            evaluation_passed=evaluation.candidate_wins,
            rollback_ready=rollback_ready,
        )

    def promotion_authorization_request(self, candidate, evidence, *, requester: str) -> PromotionAuthorizationRequest:
        from skeleton.ai.training.flgb_training_runtime import CandidateWeights, PromotionEvidence
        if not isinstance(candidate, CandidateWeights) or not isinstance(evidence, PromotionEvidence):
            raise TokenizerContractError("candidate/promotion evidence required")
        if candidate.status != "candidate":
            raise TokenizerContractError("only candidate weights may request authorization")
        if evidence.candidate_digest != candidate.digest:
            raise TokenizerContractError("promotion evidence does not belong to candidate")
        if not evidence.qualified:
            raise TokenizerContractError("unqualified promotion evidence")
        if candidate.production_authorized():
            raise TokenizerContractError("candidate unexpectedly self-authorized")
        return PromotionAuthorizationRequest(candidate.digest, evidence.digest, evidence.exact_head_commit, requester)

    def decode(self, sequence: TokenSequence, *, require_identity: bool = True) -> str:
        if not isinstance(sequence, TokenSequence):
            raise TokenizerContractError("TokenSequence required")
        self.tokenizer.assert_unchanged()
        if require_identity and sequence.tokenizer_digest != self.tokenizer.digest:
            raise TokenizerContractError("tokenizer identity mismatch")
        return self.tokenizer.decode_ids(sequence.token_ids)

    def verify_round_trip(self, text: str) -> TokenSequence:
        normalized = self.normalize(text)
        sequence = self.tokenizer.encode_sequence(normalized)
        decoded = self.decode(sequence)
        # Not every admitted legacy vocabulary is lossless. Never pretend it is.
        # Where decoding is lossless, bind the exact normalized source digest.
        if decoded == normalized:
            expected = sha256(normalized.encode("utf-8")).hexdigest()
            if sequence.source_text_digest != expected:
                raise TokenizerContractError("source digest mismatch")
        return sequence

    def stream(self, chunks: Iterable[str]) -> PreparedText:
        # Normalize only after assembly: Unicode composition and CRLF boundaries
        # can straddle arbitrary transport chunks.
        feed = StreamingTextFeed(limits=self.tokenizer.limits)
        accepted: list[str] = []
        for chunk in chunks:
            feed.push(chunk)
            accepted.append(chunk)
        # Finalize to enforce one-shot lifecycle and tokenizer admission.
        # The finalized sequence is deliberately checked against prepare() so
        # streaming can never silently use a different tokenizer identity.
        streamed = feed.finalize(self.tokenizer)
        prepared = self.prepare("".join(accepted))
        if streamed.tokenizer_digest != prepared.sequence.tokenizer_digest:
            raise TokenizerContractError("stream tokenizer identity mismatch")
        return prepared


__all__ = ["CausalTrainingBatch", "GovernedTrainingInput", "ModelInputBatch", "PipelineReplayCheckpoint", "PreparedCorpus", "PreparedText", "PromotionAuthorizationRequest", "TextPipelineConfig", "TextTokenPipeline", "TrainingInputReceipt", "materialize_causal_training_batch", "materialize_model_batch"]

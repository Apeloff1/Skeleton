"""Integrated deterministic text-to-model-input pipeline.

Composes normalization, native tokenization, context-window preparation and
bounded batching without weakening the lower-level FLGB-02 contracts.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
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
class ModelInputBatch:
    """Rectangular model-ready token ids with explicit attention semantics."""
    input_ids: tuple[tuple[int, ...], ...]
    attention_mask: tuple[tuple[int, ...], ...]
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
        if len(self.source_window_digests) != len(self.input_ids):
            raise TokenizerContractError("model batch provenance mismatch")
        if any(bit not in (0, 1) for row in self.attention_mask for bit in row):
            raise TokenizerContractError("invalid attention mask")
        for ids, mask in zip(self.input_ids, self.attention_mask):
            seen_padding = False
            for token_id, bit in zip(ids, mask):
                if bit == 0:
                    seen_padding = True
                    if token_id != self.pad_token_id:
                        raise TokenizerContractError("masked token is not padding")
                elif seen_padding:
                    raise TokenizerContractError("non-padding token after padding")

    @property
    def digest(self) -> str:
        return digest_json({"input_ids": [list(row) for row in self.input_ids], "attention_mask": [list(row) for row in self.attention_mask], "source_window_digests": list(self.source_window_digests), "pad_token_id": self.pad_token_id})


def materialize_model_batch(windows: Sequence[TokenWindow], *, pad_token_id: int) -> ModelInputBatch:
    items = tuple(windows)
    if not items:
        raise TokenizerContractError("empty model input windows")
    if isinstance(pad_token_id, bool) or not isinstance(pad_token_id, int) or pad_token_id < 0:
        raise TokenizerContractError("invalid pad_token_id")
    if any(not isinstance(window, TokenWindow) for window in items):
        raise TokenizerContractError("TokenWindow required")
    width = max(len(window.token_ids) for window in items)
    rows, masks, digests = [], [], []
    for window in items:
        padding = width - len(window.token_ids)
        rows.append(tuple(window.token_ids) + (pad_token_id,) * padding)
        masks.append((1,) * len(window.token_ids) + (0,) * padding)
        digests.append(window.digest)
    return ModelInputBatch(tuple(rows), tuple(masks), tuple(digests), pad_token_id)


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

    def __post_init__(self) -> None:
        for name in ("receipt_digest", "dataset_revision_digest", "transform_digest", "rights_digest"):
            value = getattr(self, name)
            if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
                raise TokenizerContractError(f"invalid {name}")

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
        pad = self.tokenizer.vocabulary_manifest.special_tokens["unk"] if pad_token_id is None else pad_token_id
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
        return GovernedTrainingInput(receipt.digest, dataset_revision.digest, dataset_revision.transform_digest, dataset_rights.digest)

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

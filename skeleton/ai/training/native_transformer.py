"""Governed executable training for Skeleton's native causal transformer.

This module closes the gap between FLGB-07's candidate-only training contracts
and the executable TinyTransformer used by FLGB-02.  Training never promotes
weights.  It produces a content-addressed native runtime artifact plus lineage
records that must still pass independent evaluation and promotion gates.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from pathlib import Path
import threading
from typing import Any, Iterable, Mapping, Sequence

from skeleton.ai.model_runtime import NativeLLMRuntime
from skeleton.ai.runtime.inference.artifact import (
    LocalModelArtifactError,
    LocalModelArtifactReceipt,
    load_local_model_artifact,
    write_local_model_artifact,
)
from skeleton.ai.runtime.inference.local import LocalInferenceRequest
from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel
from skeleton.cortex.bpe import BytePairEncoder
from skeleton.cortex.transformer import TinyTransformer, UNK as TRANSFORMER_UNK
from skeleton.ai.model_runtime.runtime_contracts import MAX_CHECKPOINT_BYTES

from .flgb_training_runtime import (
    CandidateWeights,
    DatasetRevision,
    DatasetRights,
    TrainingCheckpoint,
    TrainingContractError,
    TrainingManifest,
    digest_json,
    require_digest,
    require_id,
)

TRAINING_SCHEMA = "skeleton.ai.native-transformer-training.v1"
TRAINING_SCOPE = "native-transformer-training"
NORMALIZATION_SCHEMA = "utf8-crlf-to-lf-strip.v1"

MAX_DOCUMENTS = 1_000_000
MAX_DOCUMENT_CHARS = 16_000_000
MAX_CORPUS_CHARS = 1_000_000_000
MAX_DIM = 4096
MAX_CONTEXT = 32768
MAX_HEADS = 128
MAX_LAYERS = 128
MAX_FF = 32768
MAX_BPE_MERGES = 65536
MAX_EPOCHS = 10000
MAX_TRAINING_STEPS = 1_000_000_000


class NativeTrainingError(TrainingContractError):
    """Fail-closed executable native-training contract violation."""


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _positive_int(value: Any, name: str, maximum: int) -> int:
    if not _is_int(value) or not 1 <= value <= maximum:
        raise NativeTrainingError(f"invalid {name}")
    return int(value)


def _normalize_document(text: str) -> str:
    if not isinstance(text, str):
        raise NativeTrainingError("training document must be text")
    try:
        text.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise NativeTrainingError("training document must be valid UTF-8 text") from exc
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        raise NativeTrainingError("training document must be non-empty")
    if len(normalized) > MAX_DOCUMENT_CHARS:
        raise NativeTrainingError("training document exceeds character budget")
    return normalized


def normalize_documents(documents: Iterable[str]) -> tuple[str, ...]:
    values = tuple(_normalize_document(value) for value in documents)
    if not values or len(values) > MAX_DOCUMENTS:
        raise NativeTrainingError("invalid training document count")
    total = sum(len(value) for value in values)
    if total > MAX_CORPUS_CHARS:
        raise NativeTrainingError("training corpus exceeds character budget")
    digests = [sha256(value.encode("utf-8")).hexdigest() for value in values]
    if len(set(digests)) != len(digests):
        raise NativeTrainingError("duplicate training document content")
    return values


def corpus_digest(documents: Sequence[str]) -> str:
    normalized = normalize_documents(documents)
    raw = json.dumps(
        list(normalized),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(raw).hexdigest()


def normalization_digest() -> str:
    return digest_json(
        {
            "schema": NORMALIZATION_SCHEMA,
            "line_endings": "lf",
            "outer_whitespace": "strip",
            "unicode": "utf8-strict-no-normalization",
            "document_order": "preserved",
            "duplicate_content": "forbidden",
        }
    )


@dataclass(frozen=True)
class GovernedTrainingDataset:
    rights: DatasetRights
    revision: DatasetRevision
    documents: tuple[str, ...]
    training_scope: str = TRAINING_SCOPE

    def __post_init__(self) -> None:
        require_id(self.training_scope, "training_scope")
        docs = normalize_documents(self.documents)
        object.__setattr__(self, "documents", docs)
        if self.rights.dataset_id != self.revision.dataset_id:
            raise NativeTrainingError("dataset rights/revision identity mismatch")
        if not self.rights.permits(self.training_scope):
            raise NativeTrainingError("dataset rights do not permit native training")
        if self.revision.rights_digest != self.rights.digest:
            raise NativeTrainingError("dataset revision rights digest mismatch")
        if self.revision.content_digest != corpus_digest(docs):
            raise NativeTrainingError("dataset revision content digest mismatch")
        if self.revision.transform_digest != normalization_digest():
            raise NativeTrainingError("dataset revision normalization digest mismatch")

    @property
    def digest(self) -> str:
        return digest_json(
            {
                "rights_digest": self.rights.digest,
                "revision_digest": self.revision.digest,
                "training_scope": self.training_scope,
                "document_digests": [
                    sha256(value.encode("utf-8")).hexdigest()
                    for value in self.documents
                ],
            }
        )


def governed_dataset(
    *,
    dataset_id: str,
    source_id: str,
    documents: Sequence[str],
    rights_evidence_digest: str,
    license_id: str | None = None,
) -> GovernedTrainingDataset:
    """Build a genesis dataset revision from explicit rights evidence."""
    require_id(dataset_id, "dataset_id")
    require_id(source_id, "source_id")
    require_digest(rights_evidence_digest, "rights_evidence_digest")
    if license_id is not None:
        require_id(license_id, "license_id")
    docs = normalize_documents(documents)
    rights = DatasetRights(
        dataset_id=dataset_id,
        source_id=source_id,
        rights_status="allowed",
        license_id=license_id,
        allowed_scopes=(TRAINING_SCOPE,),
        evidence_digest=rights_evidence_digest,
    )
    revision = DatasetRevision(
        dataset_id=dataset_id,
        revision=0,
        content_digest=corpus_digest(docs),
        rights_digest=rights.digest,
        transform_digest=normalization_digest(),
    )
    return GovernedTrainingDataset(rights, revision, docs)


@dataclass(frozen=True)
class NativeTransformerTrainingConfig:
    dim: int = 16
    context: int = 64
    heads: int = 2
    layers: int = 2
    feed_forward: int = 32
    norm: str = "rms"
    ffn_kind: str = "swiglu"
    bpe_merges: int = 96
    epochs: int = 1
    learning_rate: float = 0.02
    schedule: str = "cosine"
    seed: int = 0
    max_steps: int = 1_000_000

    def __post_init__(self) -> None:
        _positive_int(self.dim, "dim", MAX_DIM)
        _positive_int(self.context, "context", MAX_CONTEXT)
        _positive_int(self.heads, "heads", MAX_HEADS)
        _positive_int(self.layers, "layers", MAX_LAYERS)
        _positive_int(self.feed_forward, "feed_forward", MAX_FF)
        _positive_int(self.bpe_merges, "bpe_merges", MAX_BPE_MERGES)
        _positive_int(self.epochs, "epochs", MAX_EPOCHS)
        _positive_int(self.max_steps, "max_steps", MAX_TRAINING_STEPS)
        if self.dim % self.heads:
            raise NativeTrainingError("model dimension must be divisible by heads")
        if self.norm not in {"ln", "rms"}:
            raise NativeTrainingError("unsupported training norm")
        if self.ffn_kind not in {"gelu", "swiglu"}:
            raise NativeTrainingError("unsupported training FFN")
        if self.schedule not in {"const", "cosine"}:
            raise NativeTrainingError("unsupported learning-rate schedule")
        if (
            not isinstance(self.learning_rate, (int, float))
            or isinstance(self.learning_rate, bool)
            or not math.isfinite(float(self.learning_rate))
            or not 0.0 < float(self.learning_rate) <= 1.0
        ):
            raise NativeTrainingError("invalid learning_rate")
        if not _is_int(self.seed):
            raise NativeTrainingError("seed must be an integer")

    @property
    def digest(self) -> str:
        return digest_json(self.to_dict())

    @property
    def seed_manifest_digest(self) -> str:
        return digest_json(
            {
                "schema": TRAINING_SCHEMA,
                "seed": self.seed,
                "weight_initialization": "TinyTransformer.Random.v1",
                "bpe_fit": "ordered-corpus-deterministic-counter.v1",
                "training_order": "document-order-token-window-order.v1",
            }
        )

    @property
    def optimizer_digest(self) -> str:
        return digest_json(
            {
                "algorithm": "native-sgd",
                "learning_rate": float(self.learning_rate),
                "schedule": self.schedule,
                "epochs": self.epochs,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "dim": self.dim,
            "context": self.context,
            "heads": self.heads,
            "layers": self.layers,
            "feed_forward": self.feed_forward,
            "norm": self.norm,
            "ffn_kind": self.ffn_kind,
            "bpe_merges": self.bpe_merges,
            "epochs": self.epochs,
            "learning_rate": float(self.learning_rate),
            "schedule": self.schedule,
            "seed": self.seed,
            "max_steps": self.max_steps,
        }


def _implementation_digest() -> str:
    """Digest the executable trainer and the two numerical/tokenizer owners."""
    # Resolve through imported module files so the digest is independent of cwd.
    import skeleton.cortex.bpe as bpe_module
    import skeleton.cortex.transformer as transformer_module

    real_paths = (
        Path(__file__).resolve(),
        Path(transformer_module.__file__).resolve(),
        Path(bpe_module.__file__).resolve(),
    )
    digest = sha256()
    for path in real_paths:
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise NativeTrainingError(
                "native trainer implementation source is unavailable"
            ) from exc
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256(raw).digest())
    return digest.hexdigest()


def _build_model(
    documents: Sequence[str],
    config: NativeTransformerTrainingConfig,
) -> tuple[TinyTransformer, BytePairEncoder]:
    bpe = BytePairEncoder(merges=config.bpe_merges)
    bpe.fit(documents)
    if not bpe.itos or len(set(bpe.itos)) != len(bpe.itos):
        raise NativeTrainingError("BPE produced invalid vocabulary")
    if TRANSFORMER_UNK in bpe.itos:
        raise NativeTrainingError(
            "BPE vocabulary collides with transformer reserved unknown token"
        )
    model = TinyTransformer(
        vocab=tuple(bpe.itos),
        dim=config.dim,
        ctx=config.context,
        seed=config.seed,
        n_heads=config.heads,
        n_layers=config.layers,
        d_ff=config.feed_forward,
        norm=config.norm,
        ffn_kind=config.ffn_kind,
    )
    model.bpe = bpe
    return model, bpe


def _planned_steps(
    model: TinyTransformer,
    documents: Sequence[str],
    epochs: int,
) -> int:
    per_epoch = 0
    for document in documents:
        ids = model._ids(document)
        per_epoch += max(0, len(ids) - 1)
    if per_epoch < 1:
        raise NativeTrainingError("training corpus produces no next-token windows")
    return per_epoch * epochs


@dataclass(frozen=True)
class NativeTrainingReceipt:
    schema: str
    candidate_id: str
    base_model_digest: str
    trained_model_digest: str
    tokenizer_digest: str
    dataset_digest: str
    dataset_revision_digest: str
    training_manifest_digest: str
    checkpoint_digest: str
    candidate_digest: str
    artifact_sha256: str
    artifact_reference: str
    artifact_bytes: int
    qualification_digest: str
    planned_steps: int
    completed_steps: int
    document_count: int
    initial_perplexity: float
    final_perplexity: float
    config_digest: str
    implementation_digest: str
    production_authorized: bool = False

    def __post_init__(self) -> None:
        if self.schema != TRAINING_SCHEMA:
            raise NativeTrainingError("unsupported native training receipt schema")
        require_id(self.candidate_id, "candidate_id")
        for name in (
            "base_model_digest",
            "trained_model_digest",
            "tokenizer_digest",
            "dataset_digest",
            "dataset_revision_digest",
            "training_manifest_digest",
            "checkpoint_digest",
            "candidate_digest",
            "artifact_sha256",
            "qualification_digest",
            "config_digest",
            "implementation_digest",
        ):
            require_digest(getattr(self, name), name)
        _positive_int(self.planned_steps, "planned_steps", MAX_TRAINING_STEPS)
        _positive_int(self.completed_steps, "completed_steps", MAX_TRAINING_STEPS)
        _positive_int(self.document_count, "document_count", MAX_DOCUMENTS)
        _positive_int(self.artifact_bytes, "artifact_bytes", MAX_CHECKPOINT_BYTES)
        if (
            not isinstance(self.artifact_reference, str)
            or self.artifact_reference
            != "local-model-artifact:" + self.artifact_sha256
        ):
            raise NativeTrainingError("invalid native artifact reference")
        if self.completed_steps != self.planned_steps:
            raise NativeTrainingError("training step accounting mismatch")
        for name in ("initial_perplexity", "final_perplexity"):
            value = getattr(self, name)
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(float(value))
                or float(value) <= 0.0
            ):
                raise NativeTrainingError(f"invalid {name}")
        if self.production_authorized is not False:
            raise NativeTrainingError("native training receipt cannot self-authorize production")

    @property
    def digest(self) -> str:
        return digest_json(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "candidate_id": self.candidate_id,
            "base_model_digest": self.base_model_digest,
            "trained_model_digest": self.trained_model_digest,
            "tokenizer_digest": self.tokenizer_digest,
            "dataset_digest": self.dataset_digest,
            "dataset_revision_digest": self.dataset_revision_digest,
            "training_manifest_digest": self.training_manifest_digest,
            "checkpoint_digest": self.checkpoint_digest,
            "candidate_digest": self.candidate_digest,
            "artifact_sha256": self.artifact_sha256,
            "artifact_reference": self.artifact_reference,
            "artifact_bytes": self.artifact_bytes,
            "qualification_digest": self.qualification_digest,
            "planned_steps": self.planned_steps,
            "completed_steps": self.completed_steps,
            "document_count": self.document_count,
            "initial_perplexity": float(self.initial_perplexity),
            "final_perplexity": float(self.final_perplexity),
            "config_digest": self.config_digest,
            "implementation_digest": self.implementation_digest,
            "production_authorized": False,
        }


def train_native_transformer_candidate(
    *,
    dataset: GovernedTrainingDataset,
    output_path: str | Path,
    candidate_id: str,
    config: NativeTransformerTrainingConfig | None = None,
    implementation_digest: str | None = None,
) -> NativeTrainingReceipt:
    """Train and persist one candidate-only native transformer artifact."""
    if not isinstance(dataset, GovernedTrainingDataset):
        raise NativeTrainingError("GovernedTrainingDataset required")
    candidate_id = require_id(candidate_id, "candidate_id")
    cfg = config or NativeTransformerTrainingConfig()
    if not isinstance(cfg, NativeTransformerTrainingConfig):
        raise NativeTrainingError("NativeTransformerTrainingConfig required")
    code_digest = (
        _implementation_digest()
        if implementation_digest is None
        else require_digest(implementation_digest, "implementation_digest")
    )

    model, _bpe = _build_model(dataset.documents, cfg)
    base_runtime = NativeLLMRuntime(model)
    base_digest = base_runtime.model_digest
    tokenizer_digest = base_runtime.tokenizer.digest
    planned = _planned_steps(model, dataset.documents, cfg.epochs)
    if planned > cfg.max_steps:
        raise NativeTrainingError("planned training exceeds configured step budget")

    manifest = TrainingManifest(
        run_id=candidate_id,
        base_model_digest=base_digest,
        dataset_revision_digests=(dataset.revision.digest,),
        code_digest=code_digest,
        config_digest=cfg.digest,
        seed_manifest_digest=cfg.seed_manifest_digest,
        max_steps=cfg.max_steps,
    )

    initial_perplexity = model.perplexity(dataset.documents)
    completed = 0
    for _epoch in range(cfg.epochs):
        completed += model.fit(
            dataset.documents,
            lr=float(cfg.learning_rate),
            schedule=cfg.schedule,
        )
        if completed > cfg.max_steps:
            raise NativeTrainingError("training exceeded configured step budget")
    if completed != planned:
        raise NativeTrainingError("native trainer completed unexpected step count")

    trained_runtime = NativeLLMRuntime(model)
    if trained_runtime.model_digest == base_digest:
        raise NativeTrainingError("training completed without changing model weights")
    if trained_runtime.tokenizer.digest != tokenizer_digest:
        raise NativeTrainingError("tokenizer identity changed during weight training")

    final_perplexity = model.perplexity(dataset.documents)
    checkpoint = TrainingCheckpoint(
        run_manifest_digest=manifest.digest,
        sequence=0,
        weights_digest=trained_runtime.model_digest,
        optimizer_digest=cfg.optimizer_digest,
        rng_digest=cfg.seed_manifest_digest,
    )
    lineage_digest = digest_json(
        {
            "schema": TRAINING_SCHEMA,
            "manifest_digest": manifest.digest,
            "checkpoint_digest": checkpoint.digest,
            "dataset_digest": dataset.digest,
            "base_model_digest": base_digest,
            "trained_model_digest": trained_runtime.model_digest,
        }
    )
    candidate = CandidateWeights(
        candidate_id=candidate_id,
        weights_digest=trained_runtime.model_digest,
        training_lineage_digest=lineage_digest,
        base_model_digest=base_digest,
        status="candidate",
    )
    if candidate.production_authorized():
        raise NativeTrainingError("candidate unexpectedly has production authority")

    try:
        artifact: LocalModelArtifactReceipt = write_local_model_artifact(
            NativeRuntimeLocalModel(trained_runtime),
            output_path,
        )
    except (LocalModelArtifactError, TypeError, ValueError, RuntimeError) as exc:
        raise NativeTrainingError("native candidate artifact write failed") from exc
    if artifact.model_digest != trained_runtime.model_digest:
        raise NativeTrainingError("artifact/model digest mismatch")

    try:
        loaded = load_local_model_artifact(output_path)
        if not isinstance(loaded.model, NativeRuntimeLocalModel):
            raise NativeTrainingError(
                "written native candidate reloaded as the wrong backend"
            )
        if loaded.model.model_digest != trained_runtime.model_digest:
            raise NativeTrainingError(
                "reloaded native candidate model identity mismatch"
            )
        if loaded.model.tokenizer_digest != trained_runtime.tokenizer.digest:
            raise NativeTrainingError(
                "reloaded native candidate tokenizer identity mismatch"
            )
        qualification = loaded.model.infer(
            LocalInferenceRequest(
                prompt=dataset.documents[0][0],
                max_output_tokens=1,
                seed=cfg.seed,
            ),
            threading.Event(),
        )
    except NativeTrainingError:
        raise
    except Exception as exc:
        raise NativeTrainingError(
            "native candidate execution qualification failed"
        ) from exc
    if not qualification.text or qualification.output_tokens != 1:
        raise NativeTrainingError(
            "native candidate execution qualification produced invalid output"
        )
    qualification_digest = digest_json(
        {
            "model_digest": qualification.model_digest,
            "input_tokens": qualification.input_tokens,
            "output_tokens": qualification.output_tokens,
            "text_digest": sha256(
                qualification.text.encode("utf-8")
            ).hexdigest(),
            "response_id": qualification.response_id,
        }
    )

    return NativeTrainingReceipt(
        schema=TRAINING_SCHEMA,
        candidate_id=candidate_id,
        base_model_digest=base_digest,
        trained_model_digest=trained_runtime.model_digest,
        tokenizer_digest=trained_runtime.tokenizer.digest,
        dataset_digest=dataset.digest,
        dataset_revision_digest=dataset.revision.digest,
        training_manifest_digest=manifest.digest,
        checkpoint_digest=checkpoint.digest,
        candidate_digest=candidate.digest,
        artifact_sha256=artifact.artifact_sha256,
        artifact_reference=artifact.reference,
        artifact_bytes=artifact.artifact_bytes,
        qualification_digest=qualification_digest,
        planned_steps=planned,
        completed_steps=completed,
        document_count=len(dataset.documents),
        initial_perplexity=initial_perplexity,
        final_perplexity=final_perplexity,
        config_digest=cfg.digest,
        implementation_digest=code_digest,
    )


__all__ = [
    "GovernedTrainingDataset",
    "NativeTrainingError",
    "NativeTrainingReceipt",
    "NativeTransformerTrainingConfig",
    "NORMALIZATION_SCHEMA",
    "TRAINING_SCHEMA",
    "TRAINING_SCOPE",
    "corpus_digest",
    "governed_dataset",
    "normalization_digest",
    "normalize_documents",
    "train_native_transformer_candidate",
]

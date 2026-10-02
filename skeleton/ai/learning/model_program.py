"""Provider-independent model-development program for P3."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Mapping, Protocol, Sequence

from skeleton.ai.runtime.inference import ReferenceNGramModel


class ModelProgramError(RuntimeError):
    """A model-development operation cannot be proven safe or reproducible."""


def _json(value: object) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ModelProgramError("value is not deterministic JSON") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _text(name: str, value: object, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ModelProgramError(f"{name} must be non-empty text")
    result = value.strip()
    if len(result) > maximum:
        raise ModelProgramError(f"{name} exceeds {maximum} characters")
    return result


def _sha(name: str, value: object) -> str:
    result = _text(name, value, maximum=64).lower()
    if len(result) != 64 or any(ch not in "0123456789abcdef" for ch in result):
        raise ModelProgramError(f"{name} must be lowercase sha256")
    return result


def _unique(name: str, values: Sequence[str], *, minimum: int = 0) -> tuple[str, ...]:
    result: list[str] = []
    for raw in values:
        item = _text(name, raw)
        if item in result:
            raise ModelProgramError(f"{name} contains duplicate {item}")
        result.append(item)
    if len(result) < minimum:
        raise ModelProgramError(f"{name} requires at least {minimum} entries")
    return tuple(result)


def corpus_digest(corpus: Sequence[str]) -> str:
    if not corpus:
        raise ModelProgramError("training corpus must be non-empty")
    normalized = [_text("training document", document, maximum=1_000_000) for document in corpus]
    return _digest({"schema_version": 1, "documents": normalized})


@dataclass(frozen=True, slots=True)
class TrainingDataset:
    dataset_id: str
    content_digest: str
    sample_count: int
    source_refs: tuple[str, ...]
    rights_refs: tuple[str, ...]
    lineage_refs: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "dataset_id", _text("dataset_id", self.dataset_id))
        object.__setattr__(self, "content_digest", _sha("content_digest", self.content_digest))
        if isinstance(self.sample_count, bool) or not isinstance(self.sample_count, int) or self.sample_count <= 0:
            raise ModelProgramError("sample_count must be a positive integer")
        object.__setattr__(self, "source_refs", _unique("source_ref", self.source_refs, minimum=1))
        object.__setattr__(self, "rights_refs", _unique("rights_ref", self.rights_refs, minimum=1))
        object.__setattr__(self, "lineage_refs", _unique("lineage_ref", self.lineage_refs))
        frozen = dict(self.metadata)
        _json(frozen)
        object.__setattr__(self, "metadata", frozen)

    @classmethod
    def from_corpus(
        cls,
        dataset_id: str,
        corpus: Sequence[str],
        *,
        source_refs: Sequence[str],
        rights_refs: Sequence[str],
        lineage_refs: Sequence[str] = (),
        metadata: Mapping[str, object] | None = None,
    ) -> "TrainingDataset":
        return cls(
            dataset_id=dataset_id,
            content_digest=corpus_digest(corpus),
            sample_count=len(corpus),
            source_refs=tuple(source_refs),
            rights_refs=tuple(rights_refs),
            lineage_refs=tuple(lineage_refs),
            metadata={} if metadata is None else dict(metadata),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "dataset_id": self.dataset_id,
            "content_digest": self.content_digest,
            "sample_count": self.sample_count,
            "source_refs": list(self.source_refs),
            "rights_refs": list(self.rights_refs),
            "lineage_refs": list(self.lineage_refs),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class TrainingSpec:
    run_id: str
    model_id: str
    dataset_ids: tuple[str, ...]
    trainer_id: str
    code_revision: str
    seed: int = 0
    base_model_digest: str | None = None
    hyperparameters: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _text("run_id", self.run_id))
        object.__setattr__(self, "model_id", _text("model_id", self.model_id))
        object.__setattr__(self, "dataset_ids", _unique("dataset_id", self.dataset_ids, minimum=1))
        object.__setattr__(self, "trainer_id", _text("trainer_id", self.trainer_id))
        object.__setattr__(self, "code_revision", _text("code_revision", self.code_revision, maximum=256))
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise ModelProgramError("seed must be an integer")
        if self.base_model_digest is not None:
            object.__setattr__(self, "base_model_digest", _sha("base_model_digest", self.base_model_digest))
        frozen = dict(self.hyperparameters)
        _json(frozen)
        object.__setattr__(self, "hyperparameters", frozen)

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())

    def as_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "model_id": self.model_id,
            "dataset_ids": list(self.dataset_ids),
            "trainer_id": self.trainer_id,
            "code_revision": self.code_revision,
            "seed": self.seed,
            "base_model_digest": self.base_model_digest,
            "hyperparameters": dict(self.hyperparameters),
        }


@dataclass(frozen=True, slots=True)
class ModelArtifact:
    model_id: str
    model_digest: str
    artifact_digest: str
    kind: str
    payload: Mapping[str, object]
    training_run_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "model_id", _text("model_id", self.model_id))
        object.__setattr__(self, "model_digest", _sha("model_digest", self.model_digest))
        object.__setattr__(self, "artifact_digest", _sha("artifact_digest", self.artifact_digest))
        object.__setattr__(self, "kind", _text("kind", self.kind))
        object.__setattr__(self, "training_run_id", _text("training_run_id", self.training_run_id))
        frozen = dict(self.payload)
        if _digest(frozen) != self.artifact_digest:
            raise ModelProgramError("artifact_digest does not match payload")
        object.__setattr__(self, "payload", frozen)

    def load_reference_model(self) -> ReferenceNGramModel:
        if self.kind != "reference_ngram":
            raise ModelProgramError("artifact is not a reference n-gram model")
        model = ReferenceNGramModel.from_dict(self.payload)
        if model.model_digest != self.model_digest:
            raise ModelProgramError("reloaded model identity does not match artifact")
        return model


@dataclass(frozen=True, slots=True)
class TrainingReceipt:
    run_id: str
    spec_digest: str
    dataset_digests: tuple[str, ...]
    trainer_id: str
    code_revision: str
    model_id: str
    model_digest: str
    artifact_digest: str
    metrics: Mapping[str, float]

    def __post_init__(self) -> None:
        for field_name in ("run_id", "trainer_id", "code_revision", "model_id"):
            object.__setattr__(self, field_name, _text(field_name, getattr(self, field_name)))
        for field_name in ("spec_digest", "model_digest", "artifact_digest"):
            object.__setattr__(self, field_name, _sha(field_name, getattr(self, field_name)))
        object.__setattr__(self, "dataset_digests", tuple(_sha("dataset_digest", value) for value in self.dataset_digests))
        frozen: dict[str, float] = {}
        for key, value in self.metrics.items():
            name = _text("metric name", key)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ModelProgramError(f"metric {name} must be numeric")
            frozen[name] = float(value)
        object.__setattr__(self, "metrics", frozen)

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())

    def as_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "spec_digest": self.spec_digest,
            "dataset_digests": list(self.dataset_digests),
            "trainer_id": self.trainer_id,
            "code_revision": self.code_revision,
            "model_id": self.model_id,
            "model_digest": self.model_digest,
            "artifact_digest": self.artifact_digest,
            "metrics": dict(self.metrics),
        }


@dataclass(frozen=True, slots=True)
class ModelPromotionReceipt:
    model_id: str
    model_digest: str
    training_receipt_digest: str
    evaluation_refs: tuple[str, ...]
    verifier_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "model_id", _text("model_id", self.model_id))
        object.__setattr__(self, "model_digest", _sha("model_digest", self.model_digest))
        object.__setattr__(self, "training_receipt_digest", _sha("training_receipt_digest", self.training_receipt_digest))
        object.__setattr__(self, "evaluation_refs", _unique("evaluation_ref", self.evaluation_refs, minimum=2))
        object.__setattr__(self, "verifier_id", _text("verifier_id", self.verifier_id))

    @property
    def digest(self) -> str:
        return _digest({
            "model_id": self.model_id,
            "model_digest": self.model_digest,
            "training_receipt_digest": self.training_receipt_digest,
            "evaluation_refs": list(self.evaluation_refs),
            "verifier_id": self.verifier_id,
        })


class LocalTrainer(Protocol):
    trainer_id: str

    def train(
        self,
        spec: TrainingSpec,
        corpora: Mapping[str, Sequence[str]],
    ) -> tuple[ModelArtifact, Mapping[str, float]]: ...


class ReferenceNGramTrainer:
    trainer_id = "skeleton.reference-ngram-trainer.v1"

    def train(
        self,
        spec: TrainingSpec,
        corpora: Mapping[str, Sequence[str]],
    ) -> tuple[ModelArtifact, Mapping[str, float]]:
        order_raw = spec.hyperparameters.get("order", 2)
        if isinstance(order_raw, bool) or not isinstance(order_raw, int) or not 1 <= order_raw <= 8:
            raise ModelProgramError("reference trainer order must be in [1, 8]")
        documents: list[str] = []
        for dataset_id in spec.dataset_ids:
            documents.extend(corpora[dataset_id])
        model = ReferenceNGramModel.train(documents, order=order_raw, model_id=spec.model_id)
        payload = model.to_dict()
        artifact = ModelArtifact(
            model_id=model.model_id,
            model_digest=model.model_digest,
            artifact_digest=_digest(payload),
            kind="reference_ngram",
            payload=payload,
            training_run_id=spec.run_id,
        )
        return artifact, {
            "documents": float(len(documents)),
            "tokens": float(sum(len(document.split()) for document in documents)),
            "order": float(order_raw),
        }


class ModelDevelopmentRegistry:
    def __init__(self) -> None:
        self._datasets: dict[str, TrainingDataset] = {}
        self._receipts: dict[str, TrainingReceipt] = {}
        self._artifacts: dict[str, ModelArtifact] = {}
        self._promotions: dict[str, ModelPromotionReceipt] = {}

    def register_dataset(self, dataset: TrainingDataset) -> TrainingDataset:
        if not isinstance(dataset, TrainingDataset):
            raise TypeError("dataset must be TrainingDataset")
        prior = self._datasets.get(dataset.dataset_id)
        if prior is not None and prior != dataset:
            raise ModelProgramError("dataset identity conflict")
        self._datasets[dataset.dataset_id] = dataset
        return dataset

    def train(
        self,
        spec: TrainingSpec,
        *,
        corpora: Mapping[str, Sequence[str]],
        trainer: LocalTrainer | None = None,
    ) -> tuple[ModelArtifact, TrainingReceipt]:
        if not isinstance(spec, TrainingSpec):
            raise TypeError("spec must be TrainingSpec")
        engine = trainer or ReferenceNGramTrainer()
        if engine.trainer_id != spec.trainer_id:
            raise ModelProgramError("training spec trainer_id does not match trainer")
        if spec.run_id in self._receipts:
            receipt = self._receipts[spec.run_id]
            return self._artifacts[receipt.model_digest], receipt

        checked: dict[str, tuple[str, ...]] = {}
        dataset_digests: list[str] = []
        for dataset_id in spec.dataset_ids:
            dataset = self._datasets.get(dataset_id)
            if dataset is None:
                raise ModelProgramError(f"unregistered dataset: {dataset_id}")
            corpus = corpora.get(dataset_id)
            if corpus is None:
                raise ModelProgramError(f"training corpus missing: {dataset_id}")
            normalized = tuple(_text("training document", document, maximum=1_000_000) for document in corpus)
            if len(normalized) != dataset.sample_count:
                raise ModelProgramError(f"dataset sample count drift: {dataset_id}")
            if corpus_digest(normalized) != dataset.content_digest:
                raise ModelProgramError(f"dataset content digest drift: {dataset_id}")
            checked[dataset_id] = normalized
            dataset_digests.append(dataset.content_digest)

        artifact, metrics = engine.train(spec, checked)
        receipt = TrainingReceipt(
            run_id=spec.run_id,
            spec_digest=spec.digest,
            dataset_digests=tuple(dataset_digests),
            trainer_id=engine.trainer_id,
            code_revision=spec.code_revision,
            model_id=artifact.model_id,
            model_digest=artifact.model_digest,
            artifact_digest=artifact.artifact_digest,
            metrics=metrics,
        )
        self._receipts[spec.run_id] = receipt
        self._artifacts[artifact.model_digest] = artifact
        return artifact, receipt

    def promote(
        self,
        *,
        run_id: str,
        verifier_id: str,
        evaluation_refs: Sequence[str],
    ) -> ModelPromotionReceipt:
        receipt = self._receipts.get(_text("run_id", run_id))
        if receipt is None:
            raise ModelProgramError("training receipt is unavailable")
        verifier = _text("verifier_id", verifier_id)
        if verifier == receipt.trainer_id:
            raise ModelProgramError("trainer cannot independently verify its own model")
        result = ModelPromotionReceipt(
            model_id=receipt.model_id,
            model_digest=receipt.model_digest,
            training_receipt_digest=receipt.digest,
            evaluation_refs=tuple(evaluation_refs),
            verifier_id=verifier,
        )
        self._promotions[result.model_id] = result
        return result

    def artifact(self, model_digest: str) -> ModelArtifact:
        return self._artifacts[_sha("model_digest", model_digest)]


__all__ = [
    "LocalTrainer",
    "ModelArtifact",
    "ModelDevelopmentRegistry",
    "ModelProgramError",
    "ModelPromotionReceipt",
    "ReferenceNGramTrainer",
    "TrainingDataset",
    "TrainingReceipt",
    "TrainingSpec",
    "corpus_digest",
]

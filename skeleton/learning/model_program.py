"""Provider-independent model-development program for P3."""

from __future__ import annotations

from collections.abc import Mapping as MappingABC
from dataclasses import dataclass, field
import hashlib
import json
import math
from types import MappingProxyType
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


def _freeze_json(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        _json(value)
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ModelProgramError("identity metadata contains non-finite number")
        return value
    if isinstance(value, MappingABC):
        frozen: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ModelProgramError("identity metadata keys must be strings")
            frozen[key] = _freeze_json(item)
        return MappingProxyType(dict(sorted(frozen.items())))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    raise ModelProgramError("identity metadata contains non-JSON value")


def _thaw_json(value: object) -> object:
    if isinstance(value, MappingABC):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


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
        raw_metadata = dict(self.metadata)
        _json(raw_metadata)
        object.__setattr__(self, "metadata", _freeze_json(raw_metadata))

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
            "metadata": _thaw_json(self.metadata),
        }

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema_version": "skeleton.training_dataset.v1",
                **self.as_dict(),
            }
        )


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
        raw_hyperparameters = dict(self.hyperparameters)
        _json(raw_hyperparameters)
        object.__setattr__(
            self,
            "hyperparameters",
            _freeze_json(raw_hyperparameters),
        )

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
            "hyperparameters": _thaw_json(self.hyperparameters),
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
        raw_payload = dict(self.payload)
        if _digest(raw_payload) != self.artifact_digest:
            raise ModelProgramError("artifact_digest does not match payload")
        object.__setattr__(self, "payload", _freeze_json(raw_payload))

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.model_program_artifact.v1",
            "model_id": self.model_id,
            "model_digest": self.model_digest,
            "artifact_digest": self.artifact_digest,
            "kind": self.kind,
            "payload": _thaw_json(self.payload),
            "training_run_id": self.training_run_id,
        }

    @property
    def identity_digest(self) -> str:
        return _digest(self.as_dict())

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
    dataset_identity_digests: tuple[str, ...] = ()
    integrity_binding_digests: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in ("run_id", "trainer_id", "code_revision", "model_id"):
            object.__setattr__(self, field_name, _text(field_name, getattr(self, field_name)))
        for field_name in ("spec_digest", "model_digest", "artifact_digest"):
            object.__setattr__(self, field_name, _sha(field_name, getattr(self, field_name)))
        dataset_digests = tuple(
            _sha("dataset_digest", value)
            for value in self.dataset_digests
        )
        if not dataset_digests:
            raise ModelProgramError("training receipt requires dataset digests")
        object.__setattr__(self, "dataset_digests", dataset_digests)

        dataset_identity_digests = tuple(
            _sha("dataset_identity_digest", value)
            for value in self.dataset_identity_digests
        )
        if dataset_identity_digests and (
            len(dataset_identity_digests) != len(dataset_digests)
        ):
            raise ModelProgramError(
                "dataset identity digest count must match dataset digest count"
            )
        object.__setattr__(
            self,
            "dataset_identity_digests",
            dataset_identity_digests,
        )

        integrity_binding_digests = tuple(
            _sha("integrity_binding_digest", value)
            for value in self.integrity_binding_digests
        )
        if integrity_binding_digests and (
            len(integrity_binding_digests) != len(dataset_digests)
        ):
            raise ModelProgramError(
                "integrity binding count must match dataset digest count"
            )
        object.__setattr__(
            self,
            "integrity_binding_digests",
            integrity_binding_digests,
        )

        frozen: dict[str, float] = {}
        for key, value in self.metrics.items():
            name = _text("metric name", key)
            if name in frozen:
                raise ModelProgramError("metric names collide after normalization")
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ModelProgramError(f"metric {name} must be numeric")
            number = float(value)
            if not math.isfinite(number):
                raise ModelProgramError(f"metric {name} must be finite")
            frozen[name] = number
        object.__setattr__(self, "metrics", MappingProxyType(dict(sorted(frozen.items()))))

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
            "dataset_identity_digests": list(self.dataset_identity_digests),
            "integrity_binding_digests": list(self.integrity_binding_digests),
        }


@dataclass(frozen=True, slots=True)
class TrainingAdmissionBinding:
    dataset_id: str
    dataset_identity_digest: str
    dataset_content_digest: str
    integrity_receipt_digest: str
    policy_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "dataset_id", _text("dataset_id", self.dataset_id))
        for field_name in (
            "dataset_identity_digest",
            "dataset_content_digest",
            "integrity_receipt_digest",
            "policy_digest",
        ):
            object.__setattr__(
                self,
                field_name,
                _sha(field_name, getattr(self, field_name)),
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.training_admission_binding.v1",
            "dataset_id": self.dataset_id,
            "dataset_identity_digest": self.dataset_identity_digest,
            "dataset_content_digest": self.dataset_content_digest,
            "integrity_receipt_digest": self.integrity_receipt_digest,
            "policy_digest": self.policy_digest,
        }

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class TrainingRunEvidence:
    run_id: str
    spec_digest: str
    dataset_identity_digests: tuple[str, ...]
    integrity_binding_digests: tuple[str, ...]
    artifact_identity_digest: str
    training_receipt_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _text("run_id", self.run_id))
        object.__setattr__(self, "spec_digest", _sha("spec_digest", self.spec_digest))
        dataset_ids = tuple(
            _sha("dataset_identity_digest", value)
            for value in self.dataset_identity_digests
        )
        if not dataset_ids:
            raise ModelProgramError("run evidence requires dataset identities")
        bindings = tuple(
            _sha("integrity_binding_digest", value)
            for value in self.integrity_binding_digests
        )
        if bindings and len(bindings) != len(dataset_ids):
            raise ModelProgramError(
                "run evidence integrity binding count must match datasets"
            )
        object.__setattr__(self, "dataset_identity_digests", dataset_ids)
        object.__setattr__(self, "integrity_binding_digests", bindings)
        object.__setattr__(
            self,
            "artifact_identity_digest",
            _sha("artifact_identity_digest", self.artifact_identity_digest),
        )
        object.__setattr__(
            self,
            "training_receipt_digest",
            _sha("training_receipt_digest", self.training_receipt_digest),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.training_run_evidence.v1",
            "run_id": self.run_id,
            "spec_digest": self.spec_digest,
            "dataset_identity_digests": list(self.dataset_identity_digests),
            "integrity_binding_digests": list(self.integrity_binding_digests),
            "artifact_identity_digest": self.artifact_identity_digest,
            "training_receipt_digest": self.training_receipt_digest,
        }

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())


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
    def __init__(
        self,
        *,
        require_integrity_receipts: bool = False,
        allowed_integrity_policy_digests: Sequence[str] = (),
    ) -> None:
        if not isinstance(require_integrity_receipts, bool):
            raise TypeError("require_integrity_receipts must be boolean")
        self._require_integrity_receipts = require_integrity_receipts
        policies = tuple(
            sorted(
                _sha("allowed_integrity_policy_digest", value)
                for value in allowed_integrity_policy_digests
            )
        )
        if len(policies) != len(set(policies)):
            raise ModelProgramError("allowed integrity policy digests must be unique")
        self._allowed_integrity_policy_digests = policies
        self._datasets: dict[str, TrainingDataset] = {}
        self._integrity_bindings: dict[str, TrainingAdmissionBinding] = {}
        self._receipts: dict[str, TrainingReceipt] = {}
        self._run_evidence: dict[str, TrainingRunEvidence] = {}
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

    def bind_training_integrity(
        self,
        dataset_id: str,
        receipt: object,
    ) -> TrainingAdmissionBinding:
        from skeleton.ai.learning.training_integrity import (
            TrainingIntegrityGate,
            TrainingIntegrityReceipt,
        )

        normalized_id = _text("dataset_id", dataset_id)
        dataset = self._datasets.get(normalized_id)
        if dataset is None:
            raise ModelProgramError("cannot bind integrity for unregistered dataset")
        if not isinstance(receipt, TrainingIntegrityReceipt):
            raise TypeError("receipt must be TrainingIntegrityReceipt")
        if receipt.dataset_id != dataset.dataset_id:
            raise ModelProgramError("integrity receipt dataset id mismatch")
        if receipt.dataset_digest != dataset.content_digest:
            raise ModelProgramError("integrity receipt dataset digest mismatch")
        try:
            TrainingIntegrityGate.require_admitted(receipt)
        except Exception as exc:
            raise ModelProgramError("training integrity receipt is not admitted") from exc
        if (
            self._allowed_integrity_policy_digests
            and receipt.policy_digest not in self._allowed_integrity_policy_digests
        ):
            raise ModelProgramError("training integrity policy is not allowlisted")

        binding = TrainingAdmissionBinding(
            dataset_id=dataset.dataset_id,
            dataset_identity_digest=dataset.digest,
            dataset_content_digest=dataset.content_digest,
            integrity_receipt_digest=receipt.digest,
            policy_digest=receipt.policy_digest,
        )
        prior = self._integrity_bindings.get(dataset.dataset_id)
        if prior is not None and prior != binding:
            raise ModelProgramError("training integrity binding conflict")
        self._integrity_bindings[dataset.dataset_id] = binding
        return binding

    def integrity_binding(self, dataset_id: str) -> TrainingAdmissionBinding:
        normalized_id = _text("dataset_id", dataset_id)
        try:
            return self._integrity_bindings[normalized_id]
        except KeyError as exc:
            raise ModelProgramError("training integrity binding is unavailable") from exc

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
        if not isinstance(corpora, MappingABC):
            raise TypeError("corpora must be a mapping")
        extra_corpora = set(corpora) - set(spec.dataset_ids)
        if extra_corpora:
            raise ModelProgramError(
                "training corpora contains unbound dataset ids"
            )

        checked: dict[str, tuple[str, ...]] = {}
        dataset_digests: list[str] = []
        dataset_identity_digests: list[str] = []
        integrity_binding_digests: list[str] = []
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
            dataset_identity_digests.append(dataset.digest)

            binding = self._integrity_bindings.get(dataset_id)
            if self._require_integrity_receipts and binding is None:
                raise ModelProgramError(
                    f"training integrity binding missing: {dataset_id}"
                )
            if binding is not None:
                if (
                    binding.dataset_identity_digest != dataset.digest
                    or binding.dataset_content_digest != dataset.content_digest
                ):
                    raise ModelProgramError(
                        f"training integrity binding is stale: {dataset_id}"
                    )
                if (
                    self._allowed_integrity_policy_digests
                    and binding.policy_digest
                    not in self._allowed_integrity_policy_digests
                ):
                    raise ModelProgramError(
                        f"training integrity policy is not allowlisted: {dataset_id}"
                    )
                integrity_binding_digests.append(binding.digest)

        if self._require_integrity_receipts and (
            len(integrity_binding_digests) != len(spec.dataset_ids)
        ):
            raise ModelProgramError("training integrity coverage is incomplete")

        prior_receipt = self._receipts.get(spec.run_id)
        if prior_receipt is not None:
            if prior_receipt.spec_digest != spec.digest:
                raise ModelProgramError(
                    "training run id is already bound to a different spec"
                )
            if prior_receipt.dataset_digests != tuple(dataset_digests):
                raise ModelProgramError(
                    "training run replay dataset content drift"
                )
            if (
                prior_receipt.dataset_identity_digests
                and prior_receipt.dataset_identity_digests
                != tuple(dataset_identity_digests)
            ):
                raise ModelProgramError(
                    "training run replay dataset identity drift"
                )
            if (
                prior_receipt.integrity_binding_digests
                and prior_receipt.integrity_binding_digests
                != tuple(integrity_binding_digests)
            ):
                raise ModelProgramError(
                    "training run replay integrity binding drift"
                )
            artifact = self._artifacts.get(prior_receipt.model_digest)
            if artifact is None:
                raise ModelProgramError(
                    "training run receipt has no retained artifact"
                )
            if (
                artifact.training_run_id != spec.run_id
                or artifact.model_id != spec.model_id
                or artifact.artifact_digest != prior_receipt.artifact_digest
            ):
                raise ModelProgramError(
                    "training run replay artifact binding is inconsistent"
                )
            return artifact, prior_receipt

        artifact, metrics = engine.train(spec, checked)
        if not isinstance(artifact, ModelArtifact):
            raise TypeError("trainer must return ModelArtifact")
        if not isinstance(metrics, MappingABC):
            raise TypeError("trainer metrics must be a mapping")
        if artifact.training_run_id != spec.run_id:
            raise ModelProgramError("trainer returned artifact for another run")
        if artifact.model_id != spec.model_id:
            raise ModelProgramError("trainer returned artifact for another model")

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
            dataset_identity_digests=tuple(dataset_identity_digests),
            integrity_binding_digests=tuple(integrity_binding_digests),
        )
        prior_artifact = self._artifacts.get(artifact.model_digest)
        if prior_artifact is not None and prior_artifact != artifact:
            raise ModelProgramError("model digest is already bound to another artifact")
        self._receipts[spec.run_id] = receipt
        self._artifacts[artifact.model_digest] = artifact
        self._run_evidence[spec.run_id] = TrainingRunEvidence(
            run_id=spec.run_id,
            spec_digest=spec.digest,
            dataset_identity_digests=tuple(dataset_identity_digests),
            integrity_binding_digests=tuple(integrity_binding_digests),
            artifact_identity_digest=artifact.identity_digest,
            training_receipt_digest=receipt.digest,
        )
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
        artifact = self._artifacts.get(receipt.model_digest)
        if artifact is None:
            raise ModelProgramError("promotion has no retained model artifact")
        if (
            artifact.training_run_id != receipt.run_id
            or artifact.model_id != receipt.model_id
            or artifact.artifact_digest != receipt.artifact_digest
        ):
            raise ModelProgramError("promotion artifact binding is inconsistent")
        result = ModelPromotionReceipt(
            model_id=receipt.model_id,
            model_digest=receipt.model_digest,
            training_receipt_digest=receipt.digest,
            evaluation_refs=tuple(evaluation_refs),
            verifier_id=verifier,
        )
        prior = self._promotions.get(result.model_id)
        if prior is not None:
            if prior == result:
                return prior
            raise ModelProgramError(
                "model promotion identity is already bound to another decision"
            )
        self._promotions[result.model_id] = result
        return result

    def artifact(self, model_digest: str) -> ModelArtifact:
        digest = _sha("model_digest", model_digest)
        try:
            return self._artifacts[digest]
        except KeyError as exc:
            raise ModelProgramError("model artifact is unavailable") from exc

    def training_receipt(self, run_id: str) -> TrainingReceipt:
        normalized = _text("run_id", run_id)
        try:
            return self._receipts[normalized]
        except KeyError as exc:
            raise ModelProgramError("training receipt is unavailable") from exc

    def run_evidence(self, run_id: str) -> TrainingRunEvidence:
        normalized = _text("run_id", run_id)
        try:
            return self._run_evidence[normalized]
        except KeyError as exc:
            raise ModelProgramError("training run evidence is unavailable") from exc


__all__ = [
    "LocalTrainer",
    "ModelArtifact",
    "ModelDevelopmentRegistry",
    "ModelProgramError",
    "ModelPromotionReceipt",
    "ReferenceNGramTrainer",
    "TrainingAdmissionBinding",
    "TrainingDataset",
    "TrainingReceipt",
    "TrainingRunEvidence",
    "TrainingSpec",
    "corpus_digest",
]

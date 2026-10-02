"""Deterministic, credential-free local model training.

This module is intentionally small enough to execute in CI while exercising the
real control-plane properties required by P3-T2: content-addressed datasets,
rights admission, deterministic worker assignment, resumable checkpoints,
model bills of materials, evaluation-gated promotion, and direct production of
the same ReferenceNGramModel consumed by Skeleton local inference.

The count-based reference trainer is an executable control-plane witness, not a
quality ceiling. Higher-capability open-weight trainers can implement the same
artifact/checkpoint/rights contracts without changing the surrounding runtime.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import math
import re
from typing import Any, Iterable, Mapping, Sequence

from skeleton.ai.runtime.inference import ReferenceNGramModel


_TOKEN = re.compile(r"\w+|[^\w\s]", re.UNICODE)
_EOS = "<|eos|>"
TRAINER_VERSION = "skeleton.native-ngram-trainer.v1"


class DatasetRightsError(RuntimeError):
    """Training admission failed because rights/provenance are insufficient."""


def _stable_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _digest(value: object) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(_TOKEN.findall(text))


@dataclass(frozen=True, slots=True)
class DatasetRecord:
    record_id: str
    text: str
    source_ref: str
    license_id: str
    usage_grant: str
    classification: str = "internal"
    synthetic_parent_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("record_id", "text", "source_ref", "license_id", "usage_grant"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty text")
        if self.usage_grant not in {"train", "train_eval", "eval_only"}:
            raise ValueError("unsupported usage_grant")
        if self.classification not in {"public", "internal", "confidential", "restricted"}:
            raise ValueError("unsupported classification")
        parents = tuple(dict.fromkeys(item.strip() for item in self.synthetic_parent_refs))
        if any(not item for item in parents):
            raise ValueError("synthetic_parent_refs must be non-empty")
        object.__setattr__(self, "synthetic_parent_refs", parents)

    def as_dict(self) -> dict[str, object]:
        return {
            "record_id": self.record_id,
            "text": self.text,
            "source_ref": self.source_ref,
            "license_id": self.license_id,
            "usage_grant": self.usage_grant,
            "classification": self.classification,
            "synthetic_parent_refs": list(self.synthetic_parent_refs),
        }


@dataclass(frozen=True, slots=True)
class DatasetManifest:
    dataset_id: str
    version: str
    records: tuple[DatasetRecord, ...]
    purpose: str = "local-model-training"

    def __post_init__(self) -> None:
        if not self.dataset_id.strip() or not self.version.strip() or not self.purpose.strip():
            raise ValueError("dataset identity fields must be non-empty")
        if not self.records:
            raise ValueError("dataset requires records")
        ids = [record.record_id for record in self.records]
        if len(ids) != len(set(ids)):
            raise ValueError("dataset record ids must be unique")

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "dataset_id": self.dataset_id,
            "version": self.version,
            "purpose": self.purpose,
            "records": [record.as_dict() for record in self.records],
        }


@dataclass(frozen=True, slots=True)
class DatasetQualityReport:
    dataset_digest: str
    record_count: int
    token_count: int
    duplicate_text_count: int
    trainable_record_count: int
    synthetic_record_count: int

    @property
    def passing(self) -> bool:
        return (
            self.record_count > 0
            and self.token_count > 0
            and self.trainable_record_count > 0
            and self.duplicate_text_count == 0
        )


class ContentAddressedDatasetRegistry:
    """In-memory deterministic dataset registry used by local training control."""

    def __init__(self) -> None:
        self._by_digest: dict[str, DatasetManifest] = {}
        self._by_identity: dict[tuple[str, str], str] = {}

    def register(self, manifest: DatasetManifest) -> str:
        if not isinstance(manifest, DatasetManifest):
            raise TypeError("manifest must be DatasetManifest")
        digest = manifest.digest
        identity = (manifest.dataset_id, manifest.version)
        prior = self._by_identity.get(identity)
        if prior is not None and prior != digest:
            raise ValueError("dataset identity cannot be rebound to different content")
        self._by_identity[identity] = digest
        self._by_digest[digest] = manifest
        return digest

    def get(self, digest: str) -> DatasetManifest:
        try:
            return self._by_digest[digest]
        except KeyError as exc:
            raise KeyError("unknown dataset digest") from exc

    def quality(self, manifest: DatasetManifest) -> DatasetQualityReport:
        texts = [record.text.strip() for record in manifest.records]
        trainable = sum(record.usage_grant in {"train", "train_eval"} for record in manifest.records)
        return DatasetQualityReport(
            dataset_digest=manifest.digest,
            record_count=len(manifest.records),
            token_count=sum(len(_tokens(text)) for text in texts),
            duplicate_text_count=len(texts) - len(set(texts)),
            trainable_record_count=trainable,
            synthetic_record_count=sum(bool(record.synthetic_parent_refs) for record in manifest.records),
        )

    def require_training_rights(self, manifest: DatasetManifest) -> None:
        report = self.quality(manifest)
        if not report.passing:
            raise DatasetRightsError("dataset quality gate failed")
        for record in manifest.records:
            if record.usage_grant not in {"train", "train_eval"}:
                raise DatasetRightsError(f"record lacks training grant: {record.record_id}")
            if record.classification == "restricted":
                raise DatasetRightsError(
                    f"restricted record requires an external explicit training policy: {record.record_id}"
                )
            if not record.license_id.strip() or not record.source_ref.strip():
                raise DatasetRightsError(f"record provenance is incomplete: {record.record_id}")


@dataclass(frozen=True, slots=True)
class TrainingTopology:
    worker_ids: tuple[str, ...] = ("local-worker-0",)
    generation: int = 1

    def __post_init__(self) -> None:
        workers = tuple(dict.fromkeys(item.strip() for item in self.worker_ids))
        if not workers or any(not item for item in workers):
            raise ValueError("worker_ids must contain unique non-empty values")
        if isinstance(self.generation, bool) or not isinstance(self.generation, int) or self.generation < 1:
            raise ValueError("generation must be a positive integer")
        object.__setattr__(self, "worker_ids", workers)

    def owner_for(self, work_index: int) -> str:
        return self.worker_ids[work_index % len(self.worker_ids)]


@dataclass(frozen=True, slots=True)
class NativeTrainingConfig:
    order: int = 2
    epochs: int = 1
    model_id: str = "skeleton-native-reference-v1"
    evaluation_floor: float = 0.55

    def __post_init__(self) -> None:
        if isinstance(self.order, bool) or not isinstance(self.order, int) or not 1 <= self.order <= 8:
            raise ValueError("order must be in [1, 8]")
        if isinstance(self.epochs, bool) or not isinstance(self.epochs, int) or not 1 <= self.epochs <= 64:
            raise ValueError("epochs must be in [1, 64]")
        if not self.model_id.strip():
            raise ValueError("model_id must be non-empty")
        if not 0.0 <= self.evaluation_floor <= 1.0:
            raise ValueError("evaluation_floor must be in [0, 1]")

    @property
    def digest(self) -> str:
        return _digest(
            {
                "order": self.order,
                "epochs": self.epochs,
                "model_id": self.model_id,
                "evaluation_floor": self.evaluation_floor,
                "trainer_version": TRAINER_VERSION,
            }
        )


def _serialize_counts(
    counts: Mapping[tuple[str, ...], Mapping[str, int]]
) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "context": list(context),
            "counts": dict(sorted((str(token), int(value)) for token, value in row.items())),
        }
        for context, row in sorted(counts.items(), key=lambda item: (len(item[0]), item[0]))
    )


def _deserialize_counts(
    rows: Sequence[Mapping[str, object]]
) -> dict[tuple[str, ...], Counter[str]]:
    out: dict[tuple[str, ...], Counter[str]] = {}
    for row in rows:
        context = tuple(map(str, row.get("context", [])))
        raw = row.get("counts", {})
        if not isinstance(raw, Mapping):
            raise ValueError("checkpoint count row is malformed")
        out[context] = Counter({str(key): int(value) for key, value in raw.items()})
    return out


@dataclass(frozen=True, slots=True)
class NativeTrainingCheckpoint:
    run_id: str
    dataset_digest: str
    config_digest: str
    topology_generation: int
    next_work_index: int
    count_rows: tuple[dict[str, object], ...]

    @property
    def digest(self) -> str:
        return _digest(self.as_dict(include_digest=False))

    def as_dict(self, *, include_digest: bool = True) -> dict[str, object]:
        value: dict[str, object] = {
            "schema_version": 1,
            "run_id": self.run_id,
            "dataset_digest": self.dataset_digest,
            "config_digest": self.config_digest,
            "topology_generation": self.topology_generation,
            "next_work_index": self.next_work_index,
            "count_rows": list(self.count_rows),
        }
        if include_digest:
            value["checkpoint_digest"] = self.digest
        return value

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "NativeTrainingCheckpoint":
        rows = payload.get("count_rows", [])
        if not isinstance(rows, Sequence):
            raise ValueError("checkpoint count_rows must be a sequence")
        checkpoint = cls(
            run_id=str(payload["run_id"]),
            dataset_digest=str(payload["dataset_digest"]),
            config_digest=str(payload["config_digest"]),
            topology_generation=int(payload["topology_generation"]),
            next_work_index=int(payload["next_work_index"]),
            count_rows=tuple(dict(row) for row in rows if isinstance(row, Mapping)),
        )
        claimed = payload.get("checkpoint_digest")
        if claimed is not None and claimed != checkpoint.digest:
            raise ValueError("checkpoint digest mismatch")
        return checkpoint


@dataclass(frozen=True, slots=True)
class TrainingEvaluation:
    dataset_digest: str
    model_digest: str
    observed_transitions: int
    covered_transitions: int
    coverage: float
    mean_log_probability: float
    threshold: float

    @property
    def passed(self) -> bool:
        return self.coverage >= self.threshold

    def as_dict(self) -> dict[str, object]:
        return {
            "dataset_digest": self.dataset_digest,
            "model_digest": self.model_digest,
            "observed_transitions": self.observed_transitions,
            "covered_transitions": self.covered_transitions,
            "coverage": self.coverage,
            "mean_log_probability": self.mean_log_probability,
            "threshold": self.threshold,
            "passed": self.passed,
        }


@dataclass(frozen=True, slots=True)
class ModelBillOfMaterials:
    model_id: str
    model_digest: str
    dataset_digest: str
    training_config_digest: str
    trainer_version: str
    license_ids: tuple[str, ...]
    source_refs: tuple[str, ...]

    @property
    def digest(self) -> str:
        return _digest(self.as_dict(include_digest=False))

    def as_dict(self, *, include_digest: bool = True) -> dict[str, object]:
        value: dict[str, object] = {
            "schema_version": 1,
            "model_id": self.model_id,
            "model_digest": self.model_digest,
            "dataset_digest": self.dataset_digest,
            "training_config_digest": self.training_config_digest,
            "trainer_version": self.trainer_version,
            "license_ids": list(self.license_ids),
            "source_refs": list(self.source_refs),
        }
        if include_digest:
            value["mbom_digest"] = self.digest
        return value


@dataclass(frozen=True, slots=True)
class NativeTrainingResult:
    status: str
    run_id: str
    dataset_digest: str
    config_digest: str
    topology_generation: int
    model: ReferenceNGramModel | None = None
    checkpoint: NativeTrainingCheckpoint | None = None
    evaluation: TrainingEvaluation | None = None
    mbom: ModelBillOfMaterials | None = None
    worker_assignments: tuple[tuple[int, str], ...] = ()

    def __post_init__(self) -> None:
        if self.status not in {"checkpointed", "completed"}:
            raise ValueError("invalid training result status")
        if self.status == "checkpointed" and (self.checkpoint is None or self.model is not None):
            raise ValueError("checkpointed result requires checkpoint and no final model")
        if self.status == "completed" and (
            self.model is None or self.evaluation is None or self.mbom is None
        ):
            raise ValueError("completed result requires model/evaluation/mbom")


class NativeTrainingControlPlane:
    def __init__(self, registry: ContentAddressedDatasetRegistry | None = None) -> None:
        self.registry = registry or ContentAddressedDatasetRegistry()

    def _run_id(
        self,
        manifest: DatasetManifest,
        config: NativeTrainingConfig,
    ) -> str:
        return "train:" + _digest(
            {
                "dataset": manifest.digest,
                "config": config.digest,
                "trainer": TRAINER_VERSION,
            }
        )[:32]

    @staticmethod
    def _accumulate(
        counts: dict[tuple[str, ...], Counter[str]],
        text: str,
        order: int,
    ) -> None:
        prefix: list[str] = []
        for token in list(_tokens(text)) + [_EOS]:
            for width in range(0, min(order, len(prefix)) + 1):
                context = tuple(prefix[-width:]) if width else ()
                counts.setdefault(context, Counter())[token] += 1
            prefix.append(token)

    @staticmethod
    def _evaluate(
        model: ReferenceNGramModel,
        holdout: DatasetManifest,
        threshold: float,
    ) -> TrainingEvaluation:
        payload = model.to_dict()
        tables = {
            tuple(row["context"]): dict(row["counts"])
            for row in payload["transitions"]
        }
        total = 0
        covered = 0
        log_total = 0.0
        order = int(payload["order"])
        for record in holdout.records:
            prefix: list[str] = []
            for token in list(_tokens(record.text)) + [_EOS]:
                total += 1
                row = None
                for width in range(min(order, len(prefix)), -1, -1):
                    key = tuple(prefix[-width:]) if width else ()
                    candidate = tables.get(key)
                    if candidate and token in candidate:
                        row = candidate
                        break
                if row is not None:
                    covered += 1
                    numerator = float(row[token])
                    denominator = float(sum(row.values()))
                    log_total += math.log(numerator / denominator)
                else:
                    log_total += math.log(1e-12)
                prefix.append(token)
        coverage = 0.0 if total == 0 else covered / total
        return TrainingEvaluation(
            dataset_digest=holdout.digest,
            model_digest=model.model_digest,
            observed_transitions=total,
            covered_transitions=covered,
            coverage=coverage,
            mean_log_probability=0.0 if total == 0 else log_total / total,
            threshold=threshold,
        )

    def train(
        self,
        manifest: DatasetManifest,
        config: NativeTrainingConfig,
        *,
        holdout: DatasetManifest | None = None,
        topology: TrainingTopology | None = None,
        checkpoint: NativeTrainingCheckpoint | None = None,
        stop_after_work_items: int | None = None,
    ) -> NativeTrainingResult:
        if not isinstance(manifest, DatasetManifest):
            raise TypeError("manifest must be DatasetManifest")
        if not isinstance(config, NativeTrainingConfig):
            raise TypeError("config must be NativeTrainingConfig")
        topology = topology or TrainingTopology()
        self.registry.register(manifest)
        self.registry.require_training_rights(manifest)
        if holdout is None:
            holdout = manifest
        self.registry.register(holdout)

        run_id = self._run_id(manifest, config)
        if checkpoint is None:
            counts: dict[tuple[str, ...], Counter[str]] = {}
            next_index = 0
        else:
            if checkpoint.run_id != run_id:
                raise ValueError("checkpoint run identity mismatch")
            if checkpoint.dataset_digest != manifest.digest:
                raise ValueError("checkpoint dataset mismatch")
            if checkpoint.config_digest != config.digest:
                raise ValueError("checkpoint config mismatch")
            if checkpoint.topology_generation > topology.generation:
                raise ValueError("cannot resume from future topology generation")
            counts = _deserialize_counts(checkpoint.count_rows)
            next_index = checkpoint.next_work_index

        work = [
            record
            for _epoch in range(config.epochs)
            for record in manifest.records
        ]
        if next_index > len(work):
            raise ValueError("checkpoint next_work_index exceeds training work")
        limit = len(work)
        if stop_after_work_items is not None:
            if (
                isinstance(stop_after_work_items, bool)
                or not isinstance(stop_after_work_items, int)
                or stop_after_work_items < 1
            ):
                raise ValueError("stop_after_work_items must be a positive integer")
            limit = min(limit, next_index + stop_after_work_items)

        assignments: list[tuple[int, str]] = []
        for index in range(next_index, limit):
            owner = topology.owner_for(index)
            assignments.append((index, owner))
            self._accumulate(counts, work[index].text, config.order)

        if limit < len(work):
            cp = NativeTrainingCheckpoint(
                run_id=run_id,
                dataset_digest=manifest.digest,
                config_digest=config.digest,
                topology_generation=topology.generation,
                next_work_index=limit,
                count_rows=_serialize_counts(counts),
            )
            return NativeTrainingResult(
                status="checkpointed",
                run_id=run_id,
                dataset_digest=manifest.digest,
                config_digest=config.digest,
                topology_generation=topology.generation,
                checkpoint=cp,
                worker_assignments=tuple(assignments),
            )

        model = ReferenceNGramModel(
            order=config.order,
            transitions={key: dict(value) for key, value in counts.items()},
            model_id=config.model_id,
        )
        evaluation = self._evaluate(model, holdout, config.evaluation_floor)
        if not evaluation.passed:
            raise RuntimeError(
                f"training evaluation gate failed: coverage={evaluation.coverage:.6f}"
            )
        mbom = ModelBillOfMaterials(
            model_id=model.model_id,
            model_digest=model.model_digest,
            dataset_digest=manifest.digest,
            training_config_digest=config.digest,
            trainer_version=TRAINER_VERSION,
            license_ids=tuple(sorted({record.license_id for record in manifest.records})),
            source_refs=tuple(sorted({record.source_ref for record in manifest.records})),
        )
        return NativeTrainingResult(
            status="completed",
            run_id=run_id,
            dataset_digest=manifest.digest,
            config_digest=config.digest,
            topology_generation=topology.generation,
            model=model,
            evaluation=evaluation,
            mbom=mbom,
            worker_assignments=tuple(assignments),
        )

"""Resumable provider-independent training control for P3-T2."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Mapping, Sequence

from skeleton.ai.runtime.learning_foundation.data import (
    ContentAddressedStore,
    DataPlaneError,
    DatasetRecord,
)
from skeleton.learning.model_program import (
    ModelArtifact,
    ModelDevelopmentRegistry,
    ModelProgramError,
    ReferenceNGramTrainer,
    TrainingReceipt,
    TrainingSpec,
)


class TrainingControlError(RuntimeError):
    """Training state cannot be reproduced, resumed or independently gated."""


def _json(value: object) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise TrainingControlError("value is not deterministic JSON") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _text(name: str, value: object, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TrainingControlError(f"{name} must be non-empty text")
    result = value.strip()
    if len(result) > maximum:
        raise TrainingControlError(f"{name} exceeds {maximum} characters")
    return result


def _sha(name: str, value: object) -> str:
    result = _text(name, value, maximum=64).lower()
    if len(result) != 64 or any(ch not in "0123456789abcdef" for ch in result):
        raise TrainingControlError(f"{name} must be lowercase sha256")
    return result


@dataclass(frozen=True, slots=True)
class TrainingShard:
    shard_id: str
    dataset_id: str
    worker_id: str
    ordinal: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "shard_id", _text("shard_id", self.shard_id))
        object.__setattr__(self, "dataset_id", _text("dataset_id", self.dataset_id))
        object.__setattr__(self, "worker_id", _text("worker_id", self.worker_id))
        if isinstance(self.ordinal, bool) or not isinstance(self.ordinal, int) or self.ordinal < 0:
            raise TrainingControlError("shard ordinal must be non-negative")


@dataclass(frozen=True, slots=True)
class DistributedTrainingPlan:
    run_id: str
    worker_ids: tuple[str, ...]
    min_workers: int
    shards: tuple[TrainingShard, ...]
    plan_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _text("run_id", self.run_id))
        workers = tuple(_text("worker_id", item) for item in self.worker_ids)
        if len(set(workers)) != len(workers) or not workers:
            raise TrainingControlError("worker_ids must be unique and non-empty")
        object.__setattr__(self, "worker_ids", workers)
        if isinstance(self.min_workers, bool) or not isinstance(self.min_workers, int) or not 1 <= self.min_workers <= len(workers):
            raise TrainingControlError("min_workers must be within worker inventory")
        if not self.shards:
            raise TrainingControlError("distributed plan requires shards")
        object.__setattr__(self, "plan_digest", _sha("plan_digest", self.plan_digest))


@dataclass(frozen=True, slots=True)
class TrainingObservation:
    run_id: str
    step: int
    metrics: Mapping[str, float]
    observation_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _text("run_id", self.run_id))
        if isinstance(self.step, bool) or not isinstance(self.step, int) or self.step < 0:
            raise TrainingControlError("step must be non-negative")
        normalized: dict[str, float] = {}
        for raw_name, raw_value in self.metrics.items():
            name = _text("metric", raw_name)
            if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
                raise TrainingControlError(f"metric {name} must be numeric")
            normalized[name] = float(raw_value)
        object.__setattr__(self, "metrics", normalized)
        object.__setattr__(self, "observation_digest", _sha("observation_digest", self.observation_digest))


@dataclass(frozen=True, slots=True)
class TrainingCheckpoint:
    run_id: str
    spec_digest: str
    plan_digest: str
    step: int
    model_digest: str
    training_receipt_digest: str
    payload_digest: str
    content_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _text("run_id", self.run_id))
        for name in ("spec_digest", "plan_digest", "model_digest", "training_receipt_digest", "payload_digest", "content_digest"):
            object.__setattr__(self, name, _sha(name, getattr(self, name)))
        if isinstance(self.step, bool) or not isinstance(self.step, int) or self.step <= 0:
            raise TrainingControlError("checkpoint step must be positive")


@dataclass(frozen=True, slots=True)
class RecoveryReceipt:
    run_id: str
    checkpoint_digest: str
    available_workers: tuple[str, ...]
    required_workers: int
    status: str
    receipt_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _text("run_id", self.run_id))
        object.__setattr__(self, "checkpoint_digest", _sha("checkpoint_digest", self.checkpoint_digest))
        object.__setattr__(self, "receipt_digest", _sha("receipt_digest", self.receipt_digest))
        workers = tuple(_text("worker_id", item) for item in self.available_workers)
        if len(set(workers)) != len(workers):
            raise TrainingControlError("available workers must be unique")
        object.__setattr__(self, "available_workers", workers)
        if self.status not in {"resumable", "insufficient_capacity"}:
            raise TrainingControlError("invalid recovery status")


@dataclass(frozen=True, slots=True)
class MetricGate:
    metric: str
    minimum: float | None = None
    maximum: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "metric", _text("metric", self.metric))
        if self.minimum is None and self.maximum is None:
            raise TrainingControlError("metric gate requires a bound")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise TrainingControlError("metric gate minimum exceeds maximum")


@dataclass(frozen=True, slots=True)
class TrainingEvaluationDecision:
    run_id: str
    passed: bool
    verifier_id: str
    checks: Mapping[str, bool]
    decision_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _text("run_id", self.run_id))
        object.__setattr__(self, "verifier_id", _text("verifier_id", self.verifier_id))
        object.__setattr__(self, "checks", {str(k): bool(v) for k, v in self.checks.items()})
        object.__setattr__(self, "decision_digest", _sha("decision_digest", self.decision_digest))


@dataclass(frozen=True, slots=True)
class PostTrainingReceipt:
    run_id: str
    model_digest: str
    evaluation_digest: str
    artifact_digest: str
    isolated: bool
    promotion_eligible: bool
    receipt_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _text("run_id", self.run_id))
        for name in ("model_digest", "evaluation_digest", "artifact_digest", "receipt_digest"):
            object.__setattr__(self, name, _sha(name, getattr(self, name)))
        if self.isolated is not True:
            raise TrainingControlError("post-training lab must be isolated")


@dataclass(frozen=True, slots=True)
class TrainingRun:
    spec: TrainingSpec
    plan: DistributedTrainingPlan
    artifact: ModelArtifact
    receipt: TrainingReceipt
    checkpoint: TrainingCheckpoint
    observation: TrainingObservation


class LocalTrainingControlPlane:
    """Reference control plane over the existing local model-development registry."""

    def __init__(
        self,
        *,
        registry: ModelDevelopmentRegistry | None = None,
        checkpoint_store: ContentAddressedStore | None = None,
    ) -> None:
        self.registry = registry or ModelDevelopmentRegistry()
        self.checkpoint_store = checkpoint_store or ContentAddressedStore(max_object_bytes=16 * 1024 * 1024)
        self._runs: dict[str, TrainingRun] = {}

    @staticmethod
    def plan(
        spec: TrainingSpec,
        *,
        worker_ids: Sequence[str],
        min_workers: int,
    ) -> DistributedTrainingPlan:
        workers = tuple(_text("worker_id", item) for item in worker_ids)
        if not workers or len(set(workers)) != len(workers):
            raise TrainingControlError("worker_ids must be unique and non-empty")
        if isinstance(min_workers, bool) or not isinstance(min_workers, int) or not 1 <= min_workers <= len(workers):
            raise TrainingControlError("min_workers must be within worker inventory")
        shards = tuple(
            TrainingShard(
                shard_id=f"{spec.run_id}:shard:{index}",
                dataset_id=dataset_id,
                worker_id=workers[index % len(workers)],
                ordinal=index,
            )
            for index, dataset_id in enumerate(spec.dataset_ids)
        )
        payload = {
            "run_id": spec.run_id,
            "worker_ids": list(workers),
            "min_workers": min_workers,
            "shards": [
                {
                    "shard_id": item.shard_id,
                    "dataset_id": item.dataset_id,
                    "worker_id": item.worker_id,
                    "ordinal": item.ordinal,
                }
                for item in shards
            ],
        }
        return DistributedTrainingPlan(
            run_id=spec.run_id,
            worker_ids=workers,
            min_workers=min_workers,
            shards=shards,
            plan_digest=_digest(payload),
        )

    def run(
        self,
        spec: TrainingSpec,
        *,
        datasets: Sequence[DatasetRecord],
        corpora: Mapping[str, Sequence[str]],
        worker_ids: Sequence[str],
        min_workers: int = 1,
    ) -> TrainingRun:
        if not isinstance(spec, TrainingSpec):
            raise TypeError("spec must be TrainingSpec")
        if spec.run_id in self._runs:
            return self._runs[spec.run_id]

        by_identity = {record.identity: record for record in datasets}
        if set(by_identity) != set(spec.dataset_ids):
            raise TrainingControlError("training spec dataset identity coverage drift")
        for record in datasets:
            try:
                training_dataset = record.as_training_dataset()
            except DataPlaneError as exc:
                raise TrainingControlError(str(exc)) from exc
            self.registry.register_dataset(training_dataset)

        plan = self.plan(spec, worker_ids=worker_ids, min_workers=min_workers)
        try:
            artifact, receipt = self.registry.train(
                spec,
                corpora=corpora,
                trainer=ReferenceNGramTrainer(),
            )
        except ModelProgramError as exc:
            raise TrainingControlError(str(exc)) from exc

        observation_payload = {
            "run_id": spec.run_id,
            "step": 1,
            "metrics": dict(receipt.metrics),
        }
        observation = TrainingObservation(
            run_id=spec.run_id,
            step=1,
            metrics=receipt.metrics,
            observation_digest=_digest(observation_payload),
        )
        checkpoint_payload = {
            "schema_version": 1,
            "run_id": spec.run_id,
            "spec_digest": spec.digest,
            "plan_digest": plan.plan_digest,
            "step": 1,
            "model_digest": artifact.model_digest,
            "training_receipt_digest": receipt.digest,
            "artifact_digest": artifact.artifact_digest,
        }
        payload_bytes = _json(checkpoint_payload).encode("utf-8")
        content = self.checkpoint_store.put(payload_bytes, media_type="application/vnd.skeleton.training-checkpoint+json")
        checkpoint = TrainingCheckpoint(
            run_id=spec.run_id,
            spec_digest=spec.digest,
            plan_digest=plan.plan_digest,
            step=1,
            model_digest=artifact.model_digest,
            training_receipt_digest=receipt.digest,
            payload_digest=_digest(checkpoint_payload),
            content_digest=content.digest,
        )
        result = TrainingRun(
            spec=spec,
            plan=plan,
            artifact=artifact,
            receipt=receipt,
            checkpoint=checkpoint,
            observation=observation,
        )
        self._runs[spec.run_id] = result
        return result

    def recover(
        self,
        checkpoint: TrainingCheckpoint,
        *,
        available_workers: Sequence[str],
        required_workers: int,
    ) -> RecoveryReceipt:
        payload = self.checkpoint_store.get(checkpoint.content_digest)
        if hashlib.sha256(payload).hexdigest() != checkpoint.content_digest:
            raise TrainingControlError("checkpoint content digest mismatch")
        workers = tuple(_text("worker_id", item) for item in available_workers)
        if len(set(workers)) != len(workers):
            raise TrainingControlError("available workers must be unique")
        if isinstance(required_workers, bool) or not isinstance(required_workers, int) or required_workers <= 0:
            raise TrainingControlError("required_workers must be positive")
        status = "resumable" if len(workers) >= required_workers else "insufficient_capacity"
        payload_obj = {
            "run_id": checkpoint.run_id,
            "checkpoint_digest": checkpoint.content_digest,
            "available_workers": list(workers),
            "required_workers": required_workers,
            "status": status,
        }
        return RecoveryReceipt(
            run_id=checkpoint.run_id,
            checkpoint_digest=checkpoint.content_digest,
            available_workers=workers,
            required_workers=required_workers,
            status=status,
            receipt_digest=_digest(payload_obj),
        )

    def evaluate(
        self,
        run_id: str,
        *,
        gates: Sequence[MetricGate],
        verifier_id: str,
    ) -> TrainingEvaluationDecision:
        rid = _text("run_id", run_id)
        try:
            run = self._runs[rid]
        except KeyError as exc:
            raise TrainingControlError("unknown training run") from exc
        verifier = _text("verifier_id", verifier_id)
        if verifier == run.receipt.trainer_id:
            raise TrainingControlError("trainer cannot independently verify training gate")
        checks: dict[str, bool] = {}
        for gate in gates:
            if not isinstance(gate, MetricGate):
                raise TypeError("gates must contain MetricGate")
            value = run.receipt.metrics.get(gate.metric)
            ok = value is not None
            if value is not None and gate.minimum is not None:
                ok = ok and value >= gate.minimum
            if value is not None and gate.maximum is not None:
                ok = ok and value <= gate.maximum
            checks[gate.metric] = bool(ok)
        passed = bool(checks) and all(checks.values())
        payload = {
            "run_id": rid,
            "passed": passed,
            "verifier_id": verifier,
            "checks": checks,
            "training_receipt_digest": run.receipt.digest,
        }
        return TrainingEvaluationDecision(
            run_id=rid,
            passed=passed,
            verifier_id=verifier,
            checks=checks,
            decision_digest=_digest(payload),
        )

    def post_train(
        self,
        run_id: str,
        decision: TrainingEvaluationDecision,
    ) -> PostTrainingReceipt:
        rid = _text("run_id", run_id)
        try:
            run = self._runs[rid]
        except KeyError as exc:
            raise TrainingControlError("unknown training run") from exc
        if decision.run_id != rid:
            raise TrainingControlError("evaluation decision run mismatch")
        payload = {
            "run_id": rid,
            "model_digest": run.artifact.model_digest,
            "evaluation_digest": decision.decision_digest,
            "artifact_digest": run.artifact.artifact_digest,
            "isolated": True,
            "promotion_eligible": decision.passed,
        }
        return PostTrainingReceipt(
            run_id=rid,
            model_digest=run.artifact.model_digest,
            evaluation_digest=decision.decision_digest,
            artifact_digest=run.artifact.artifact_digest,
            isolated=True,
            promotion_eligible=decision.passed,
            receipt_digest=_digest(payload),
        )


__all__ = [
    "DistributedTrainingPlan",
    "LocalTrainingControlPlane",
    "MetricGate",
    "PostTrainingReceipt",
    "RecoveryReceipt",
    "TrainingCheckpoint",
    "TrainingControlError",
    "TrainingEvaluationDecision",
    "TrainingObservation",
    "TrainingRun",
    "TrainingShard",
]

"""Durable provider-independent native training orchestration.

This control plane composes the P3 model-development program with the native
content-addressed dataset repository.  It adds the lifecycle guarantees that a
trainer alone cannot provide: exact dataset-manifest binding, deterministic
sharding, durable state/checkpoints, cancellation, idempotent resume, and
artifact/receipt persistence.

The reference trainer remains a portable acceptance backend.  More capable
operator-owned trainers can implement the existing LocalTrainer contract without
changing this lifecycle or introducing hosted-provider authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
from typing import Any, Mapping, Sequence

from skeleton.data.native_pipeline import (
    DatasetVersion,
    NativeDatasetRepository,
    NativeDataError,
)
from skeleton.learning.model_program import (
    LocalTrainer,
    ModelArtifact,
    ModelDevelopmentRegistry,
    ModelProgramError,
    ReferenceNGramTrainer,
    TrainingDataset,
    TrainingReceipt,
    TrainingSpec,
    corpus_digest,
)


class NativeTrainingError(RuntimeError):
    """Native training lifecycle cannot safely continue."""


class TrainingCancelled(NativeTrainingError):
    """Training run was cancelled before model mutation."""


class TrainingState(str, Enum):
    CREATED = "created"
    PREPARED = "prepared"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


def _json(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise NativeTrainingError("training evidence must be canonical JSON") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _text(name: str, value: object, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value.strip():
        raise NativeTrainingError(f"{name} must be non-empty text")
    result = value.strip()
    if result != value or len(result) > maximum:
        raise NativeTrainingError(f"{name} is not canonical")
    return result


def _aware(value: datetime | None) -> datetime:
    instant = value or datetime.now(timezone.utc)
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise NativeTrainingError("timestamp must be timezone-aware")
    return instant.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class TrainingShard:
    shard_index: int
    row_indices: tuple[int, ...]
    digest: str

    def __post_init__(self) -> None:
        if (
            isinstance(self.shard_index, bool)
            or not isinstance(self.shard_index, int)
            or self.shard_index < 0
        ):
            raise NativeTrainingError("shard_index must be >= 0")
        if not self.row_indices:
            raise NativeTrainingError("training shard must own at least one row")
        if tuple(sorted(set(self.row_indices))) != self.row_indices:
            raise NativeTrainingError("training shard row indices must be sorted unique")
        expected = _digest(
            {"shard_index": self.shard_index, "row_indices": self.row_indices}
        )
        if self.digest != expected:
            raise NativeTrainingError("training shard digest mismatch")


@dataclass(frozen=True, slots=True)
class TrainingPlan:
    run_id: str
    dataset_manifest_digest: str
    row_count: int
    shard_count: int
    shards: tuple[TrainingShard, ...]
    text_field: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _text("run_id", self.run_id))
        object.__setattr__(self, "text_field", _text("text_field", self.text_field))
        if self.row_count < 1 or self.shard_count < 1:
            raise NativeTrainingError("row_count and shard_count must be positive")
        if len(self.shards) != self.shard_count:
            raise NativeTrainingError("shard_count mismatch")
        coverage = [index for shard in self.shards for index in shard.row_indices]
        if sorted(coverage) != list(range(self.row_count)):
            raise NativeTrainingError("training shards must cover every row exactly once")

    @property
    def digest(self) -> str:
        return _digest(
            {
                "run_id": self.run_id,
                "dataset_manifest_digest": self.dataset_manifest_digest,
                "row_count": self.row_count,
                "shard_count": self.shard_count,
                "text_field": self.text_field,
                "shards": [
                    {
                        "shard_index": shard.shard_index,
                        "row_indices": shard.row_indices,
                        "digest": shard.digest,
                    }
                    for shard in self.shards
                ],
            }
        )


@dataclass(frozen=True, slots=True)
class NativeTrainingRequest:
    tenant_id: str
    run_id: str
    dataset_id: str
    dataset_version: int
    dataset_manifest_digest: str
    text_field: str
    model_id: str
    code_revision: str
    seed: int = 0
    shard_count: int = 1
    hyperparameters: Mapping[str, object] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        for field in (
            "tenant_id",
            "run_id",
            "dataset_id",
            "dataset_manifest_digest",
            "text_field",
            "model_id",
            "code_revision",
        ):
            object.__setattr__(self, field, _text(field, getattr(self, field)))
        if (
            len(self.dataset_manifest_digest) != 64
            or any(ch not in "0123456789abcdef" for ch in self.dataset_manifest_digest)
        ):
            raise NativeTrainingError("dataset_manifest_digest must be lowercase sha256")
        if isinstance(self.dataset_version, bool) or not isinstance(self.dataset_version, int) or self.dataset_version < 1:
            raise NativeTrainingError("dataset_version must be >= 1")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise NativeTrainingError("seed must be an integer")
        if isinstance(self.shard_count, bool) or not isinstance(self.shard_count, int) or not 1 <= self.shard_count <= 1024:
            raise NativeTrainingError("shard_count must be in [1, 1024]")
        frozen = {} if self.hyperparameters is None else dict(self.hyperparameters)
        _json(frozen)
        object.__setattr__(self, "hyperparameters", frozen)

    @property
    def digest(self) -> str:
        return _digest(
            {
                "tenant_id": self.tenant_id,
                "run_id": self.run_id,
                "dataset_id": self.dataset_id,
                "dataset_version": self.dataset_version,
                "dataset_manifest_digest": self.dataset_manifest_digest,
                "text_field": self.text_field,
                "model_id": self.model_id,
                "code_revision": self.code_revision,
                "seed": self.seed,
                "shard_count": self.shard_count,
                "hyperparameters": dict(self.hyperparameters),
            }
        )


@dataclass(frozen=True, slots=True)
class NativeTrainingResult:
    run_id: str
    state: TrainingState
    request_digest: str
    plan_digest: str
    dataset_manifest_digest: str
    model_id: str | None = None
    model_digest: str | None = None
    artifact_digest: str | None = None
    training_receipt_digest: str | None = None
    artifact_cas_digest: str | None = None
    checkpoint_version: int = 0

    @property
    def completed(self) -> bool:
        return self.state is TrainingState.COMPLETED


def build_training_plan(
    request: NativeTrainingRequest,
    dataset: DatasetVersion,
) -> TrainingPlan:
    if dataset.manifest_digest != request.dataset_manifest_digest:
        raise NativeTrainingError("training request manifest does not match dataset")
    if dataset.version != request.dataset_version:
        raise NativeTrainingError("training request dataset version drift")
    shard_count = min(request.shard_count, dataset.row_count)
    buckets: list[list[int]] = [[] for _ in range(shard_count)]
    for index in range(dataset.row_count):
        bucket = int(
            hashlib.sha256(
                f"{request.seed}:{dataset.manifest_digest}:{index}".encode("utf-8")
            ).hexdigest()[:16],
            16,
        ) % shard_count
        buckets[bucket].append(index)
    # Hash partitioning can leave a tiny dataset bucket empty. Deterministically
    # compact empty buckets while preserving exact single ownership.
    compact = [tuple(sorted(bucket)) for bucket in buckets if bucket]
    shards = tuple(
        TrainingShard(
            shard_index=index,
            row_indices=rows,
            digest=_digest({"shard_index": index, "row_indices": rows}),
        )
        for index, rows in enumerate(compact)
    )
    return TrainingPlan(
        run_id=request.run_id,
        dataset_manifest_digest=dataset.manifest_digest,
        row_count=dataset.row_count,
        shard_count=len(shards),
        shards=shards,
        text_field=request.text_field,
    )


class SQLiteTrainingRunStore:
    """Durable lifecycle journal for local training runs."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._connection = sqlite3.connect(
            str(path),
            check_same_thread=False,
            timeout=5.0,
            isolation_level=None,
        )
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                PRAGMA synchronous = FULL;
                PRAGMA busy_timeout = 5000;

                CREATE TABLE IF NOT EXISTS native_training_run (
                    run_id TEXT PRIMARY KEY,
                    request_digest TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    state TEXT NOT NULL,
                    plan_digest TEXT,
                    plan_json TEXT,
                    checkpoint_version INTEGER NOT NULL,
                    result_json TEXT,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def create(self, request: NativeTrainingRequest, *, now: datetime | None = None) -> None:
        instant = _aware(now)
        payload = {
            "tenant_id": request.tenant_id,
            "run_id": request.run_id,
            "dataset_id": request.dataset_id,
            "dataset_version": request.dataset_version,
            "dataset_manifest_digest": request.dataset_manifest_digest,
            "text_field": request.text_field,
            "model_id": request.model_id,
            "code_revision": request.code_revision,
            "seed": request.seed,
            "shard_count": request.shard_count,
            "hyperparameters": dict(request.hyperparameters),
        }
        with self._lock:
            row = self._connection.execute(
                "SELECT request_digest FROM native_training_run WHERE run_id = ?",
                (request.run_id,),
            ).fetchone()
            if row is not None:
                if row["request_digest"] != request.digest:
                    raise NativeTrainingError("run_id is bound to a different request")
                return
            self._connection.execute(
                """
                INSERT INTO native_training_run(
                    run_id, request_digest, request_json, state,
                    checkpoint_version, updated_at
                ) VALUES (?, ?, ?, ?, 0, ?)
                """,
                (
                    request.run_id,
                    request.digest,
                    _json(payload),
                    TrainingState.CREATED.value,
                    instant.isoformat(),
                ),
            )

    def row(self, run_id: str) -> sqlite3.Row:
        row = self._connection.execute(
            "SELECT * FROM native_training_run WHERE run_id = ?",
            (_text("run_id", run_id),),
        ).fetchone()
        if row is None:
            raise NativeTrainingError("unknown training run")
        return row

    def transition(
        self,
        run_id: str,
        *,
        expected: Sequence[TrainingState],
        target: TrainingState,
        plan: TrainingPlan | None = None,
        result: NativeTrainingResult | None = None,
        now: datetime | None = None,
    ) -> int:
        instant = _aware(now)
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self.row(run_id)
                current = TrainingState(row["state"])
                if current not in set(expected):
                    raise NativeTrainingError(
                        f"training transition rejected: {current.value}->{target.value}"
                    )
                version = int(row["checkpoint_version"]) + 1
                plan_json = row["plan_json"]
                plan_digest = row["plan_digest"]
                if plan is not None:
                    plan_digest = plan.digest
                    plan_json = _json(
                        {
                            "run_id": plan.run_id,
                            "dataset_manifest_digest": plan.dataset_manifest_digest,
                            "row_count": plan.row_count,
                            "shard_count": plan.shard_count,
                            "text_field": plan.text_field,
                            "shards": [
                                {
                                    "shard_index": s.shard_index,
                                    "row_indices": s.row_indices,
                                    "digest": s.digest,
                                }
                                for s in plan.shards
                            ],
                        }
                    )
                result_json = row["result_json"]
                if result is not None:
                    result_json = _json(
                        {
                            "run_id": result.run_id,
                            "state": result.state.value,
                            "request_digest": result.request_digest,
                            "plan_digest": result.plan_digest,
                            "dataset_manifest_digest": result.dataset_manifest_digest,
                            "model_id": result.model_id,
                            "model_digest": result.model_digest,
                            "artifact_digest": result.artifact_digest,
                            "training_receipt_digest": result.training_receipt_digest,
                            "artifact_cas_digest": result.artifact_cas_digest,
                            "checkpoint_version": version,
                        }
                    )
                self._connection.execute(
                    """
                    UPDATE native_training_run
                    SET state = ?, plan_digest = ?, plan_json = ?,
                        result_json = ?, checkpoint_version = ?, updated_at = ?
                    WHERE run_id = ?
                    """,
                    (
                        target.value,
                        plan_digest,
                        plan_json,
                        result_json,
                        version,
                        instant.isoformat(),
                        run_id,
                    ),
                )
                self._connection.execute("COMMIT")
                return version
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def request_cancel(self, run_id: str) -> None:
        with self._lock:
            row = self.row(run_id)
            state = TrainingState(row["state"])
            if state in {TrainingState.COMPLETED, TrainingState.CANCELLED, TrainingState.FAILED}:
                return
            self._connection.execute(
                "UPDATE native_training_run SET cancel_requested = 1 WHERE run_id = ?",
                (run_id,),
            )

    def cancelled(self, run_id: str) -> bool:
        return bool(self.row(run_id)["cancel_requested"])

    def result(self, run_id: str) -> NativeTrainingResult | None:
        row = self.row(run_id)
        raw = row["result_json"]
        if raw is None:
            return None
        payload = json.loads(raw)
        return NativeTrainingResult(
            run_id=payload["run_id"],
            state=TrainingState(payload["state"]),
            request_digest=payload["request_digest"],
            plan_digest=payload["plan_digest"],
            dataset_manifest_digest=payload["dataset_manifest_digest"],
            model_id=payload["model_id"],
            model_digest=payload["model_digest"],
            artifact_digest=payload["artifact_digest"],
            training_receipt_digest=payload["training_receipt_digest"],
            artifact_cas_digest=payload["artifact_cas_digest"],
            checkpoint_version=int(row["checkpoint_version"]),
        )

    def close(self) -> None:
        self._connection.close()


class NativeTrainingController:
    """Idempotent local training lifecycle over durable dataset manifests."""

    def __init__(
        self,
        datasets: NativeDatasetRepository,
        runs: SQLiteTrainingRunStore,
        *,
        trainer: LocalTrainer | None = None,
    ) -> None:
        self.datasets = datasets
        self.runs = runs
        self.trainer = trainer or ReferenceNGramTrainer()

    def prepare(
        self,
        request: NativeTrainingRequest,
        *,
        now: datetime | None = None,
    ) -> TrainingPlan:
        self.runs.create(request, now=now)
        row = self.runs.row(request.run_id)
        state = TrainingState(row["state"])
        if state is TrainingState.COMPLETED:
            raise NativeTrainingError("completed run has no mutable prepare phase")
        dataset, rows = self.datasets.get(
            tenant_id=request.tenant_id,
            dataset_id=request.dataset_id,
            version=request.dataset_version,
        )
        if dataset.manifest_digest != request.dataset_manifest_digest:
            raise NativeTrainingError("dataset manifest changed before training")
        for index, item in enumerate(rows):
            value = item.get(request.text_field)
            if not isinstance(value, str) or not value.strip():
                raise NativeTrainingError(
                    f"training text field missing/empty at row {index}"
                )
        plan = build_training_plan(request, dataset)
        if state is TrainingState.CREATED:
            self.runs.transition(
                request.run_id,
                expected=(TrainingState.CREATED,),
                target=TrainingState.PREPARED,
                plan=plan,
                now=now,
            )
        else:
            if row["plan_digest"] != plan.digest:
                raise NativeTrainingError("recomputed training plan drift")
        return plan

    def execute(
        self,
        request: NativeTrainingRequest,
        *,
        rights_refs: Sequence[str],
        source_refs: Sequence[str],
        now: datetime | None = None,
    ) -> NativeTrainingResult:
        existing = None
        try:
            existing = self.runs.result(request.run_id)
        except NativeTrainingError:
            pass
        if existing is not None and existing.completed:
            return existing

        plan = self.prepare(request, now=now)
        if self.runs.cancelled(request.run_id):
            version = self.runs.transition(
                request.run_id,
                expected=(TrainingState.PREPARED,),
                target=TrainingState.CANCELLED,
                now=now,
            )
            raise TrainingCancelled(
                f"training cancelled at checkpoint {version}"
            )

        row = self.runs.row(request.run_id)
        state = TrainingState(row["state"])
        if state is TrainingState.PREPARED:
            self.runs.transition(
                request.run_id,
                expected=(TrainingState.PREPARED,),
                target=TrainingState.RUNNING,
                now=now,
            )
        elif state is not TrainingState.RUNNING:
            raise NativeTrainingError(f"cannot execute run in state {state.value}")

        dataset, rows = self.datasets.get(
            tenant_id=request.tenant_id,
            dataset_id=request.dataset_id,
            version=request.dataset_version,
        )
        corpus = tuple(str(item[request.text_field]).strip() for item in rows)
        training_dataset = TrainingDataset(
            dataset_id=dataset.manifest_digest,
            content_digest=corpus_digest(corpus),
            sample_count=len(corpus),
            source_refs=tuple(source_refs),
            rights_refs=tuple(rights_refs),
            lineage_refs=(dataset.manifest_digest, *dataset.parent_manifest_digests),
            metadata={
                "dataset_id": dataset.dataset_id,
                "dataset_version": dataset.version,
                "payload_digest": dataset.payload_digest,
                "schema_digest": dataset.schema_digest,
                "quality_digest": dataset.quality_digest,
            },
        )
        spec = TrainingSpec(
            run_id=request.run_id,
            model_id=request.model_id,
            dataset_ids=(training_dataset.dataset_id,),
            trainer_id=self.trainer.trainer_id,
            code_revision=request.code_revision,
            seed=request.seed,
            hyperparameters=dict(request.hyperparameters),
        )
        registry = ModelDevelopmentRegistry()
        registry.register_dataset(training_dataset)
        try:
            artifact, receipt = registry.train(
                spec,
                corpora={training_dataset.dataset_id: corpus},
                trainer=self.trainer,
            )
        except (ModelProgramError, KeyError) as exc:
            self.runs.transition(
                request.run_id,
                expected=(TrainingState.RUNNING,),
                target=TrainingState.FAILED,
                now=now,
            )
            raise NativeTrainingError("local trainer failed") from exc

        if self.runs.cancelled(request.run_id):
            self.runs.transition(
                request.run_id,
                expected=(TrainingState.RUNNING,),
                target=TrainingState.CANCELLED,
                now=now,
            )
            raise TrainingCancelled("training cancelled before artifact commit")

        artifact_payload = _json(
            {
                "schema_version": 1,
                "kind": artifact.kind,
                "model_id": artifact.model_id,
                "model_digest": artifact.model_digest,
                "artifact_digest": artifact.artifact_digest,
                "training_run_id": artifact.training_run_id,
                "payload": dict(artifact.payload),
                "receipt": receipt.as_dict(),
            }
        ).encode("utf-8")
        artifact_cas_digest = self.datasets.cas.put(artifact_payload)
        result = NativeTrainingResult(
            run_id=request.run_id,
            state=TrainingState.COMPLETED,
            request_digest=request.digest,
            plan_digest=plan.digest,
            dataset_manifest_digest=dataset.manifest_digest,
            model_id=artifact.model_id,
            model_digest=artifact.model_digest,
            artifact_digest=artifact.artifact_digest,
            training_receipt_digest=receipt.digest,
            artifact_cas_digest=artifact_cas_digest,
        )
        version = self.runs.transition(
            request.run_id,
            expected=(TrainingState.RUNNING,),
            target=TrainingState.COMPLETED,
            result=result,
            now=now,
        )
        return NativeTrainingResult(
            run_id=result.run_id,
            state=result.state,
            request_digest=result.request_digest,
            plan_digest=result.plan_digest,
            dataset_manifest_digest=result.dataset_manifest_digest,
            model_id=result.model_id,
            model_digest=result.model_digest,
            artifact_digest=result.artifact_digest,
            training_receipt_digest=result.training_receipt_digest,
            artifact_cas_digest=result.artifact_cas_digest,
            checkpoint_version=version,
        )


__all__ = [
    "NativeTrainingController",
    "NativeTrainingError",
    "NativeTrainingRequest",
    "NativeTrainingResult",
    "SQLiteTrainingRunStore",
    "TrainingCancelled",
    "TrainingPlan",
    "TrainingShard",
    "TrainingState",
    "build_training_plan",
]

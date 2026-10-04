"""Executable local reference-model training bound to durable P3 training state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from typing import Sequence

from skeleton.ai.runtime.inference import ReferenceNGramModel

from .control import (
    TrainingCheckpoint,
    TrainingRepository,
    TrainingRunManifest,
    TrainingStateError,
    TrainingTelemetry,
)
from .data import DatasetRegistry


def _digest_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def corpus_digest(corpus: Sequence[str]) -> str:
    if not corpus or any(not isinstance(item, str) or not item.strip() for item in corpus):
        raise ValueError("training corpus must contain non-empty text documents")
    return _digest_bytes("\n".join(corpus).encode("utf-8"))


@dataclass(frozen=True, slots=True)
class LocalTrainingArtifact:
    run_id: str
    run_manifest_digest: str
    dataset_digest: str
    model_id: str
    model_digest: str
    checkpoint_digest: str
    corpus_digest: str
    document_count: int

    def __post_init__(self) -> None:
        if self.document_count <= 0:
            raise ValueError("document_count must be positive")


class ReferenceLocalTrainer:
    """Train the executable local n-gram model under the durable control plane."""

    @staticmethod
    def _enforce_execution_boundary(
        manifest: TrainingRunManifest,
        corpus: Sequence[str],
    ) -> tuple[int, int]:
        """Fail closed before mutating run state when local execution exceeds authority."""
        if manifest.world_size != 1 or manifest.parallelism != "single":
            raise TrainingStateError(
                "reference local trainer only supports world_size=1 and parallelism=single"
            )

        token_count=sum(len(item.split()) for item in corpus)
        corpus_bytes=len("\n".join(corpus).encode("utf-8"))
        observed={
            "max_steps": float(token_count),
            "max_documents": float(len(corpus)),
            "max_corpus_bytes": float(corpus_bytes),
        }
        for budget_name, actual in observed.items():
            limit=manifest.resource_budget.get(budget_name)
            if limit is not None and actual > float(limit):
                raise TrainingStateError(
                    f"training budget exceeded: {budget_name} "
                    f"(actual={actual:g}, limit={float(limit):g})"
                )
        return token_count, corpus_bytes

    def __init__(
        self,
        datasets: DatasetRegistry,
        runs: TrainingRepository,
    ) -> None:
        self.datasets=datasets
        self.runs=runs

    def train(
        self,
        manifest: TrainingRunManifest,
        corpus: Sequence[str],
        *,
        split_name: str = "train",
        order: int = 2,
        worker_id: str = "local-trainer",
        now: datetime | None = None,
    ) -> tuple[ReferenceNGramModel, LocalTrainingArtifact]:
        instant=now or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        dataset=self.datasets.require_training_ready(manifest.dataset_digest)
        split=next((item for item in dataset.splits if item.name==split_name),None)
        if split is None:
            raise ValueError(f"dataset split not found: {split_name}")
        actual_corpus_digest=corpus_digest(corpus)
        if split.digest!=actual_corpus_digest:
            raise ValueError("training corpus bytes do not match registered split digest")
        token_count,_=self._enforce_execution_boundary(manifest,corpus)

        try:
            registered=self.runs.manifest(manifest.run_id)
        except KeyError:
            self.runs.register_run(manifest,self.datasets,created_at=instant)
        else:
            if registered.digest!=manifest.digest:
                raise ValueError("registered training manifest identity drift")

        state=self.runs.state(manifest.run_id)
        if state=="registered":
            self.runs.start(manifest.run_id)
        elif state=="recovering":
            self.runs.start(manifest.run_id)
        elif state!="running":
            raise ValueError(f"training run cannot execute from state {state}")

        lease=self.runs.lease_worker(manifest.run_id,worker_id,issued_at=instant)
        try:
            self.runs.record_telemetry(
                TrainingTelemetry(
                    run_id=manifest.run_id,
                    step=0,
                    metrics={"documents":float(len(corpus)),"world_size":float(manifest.world_size)},
                    emitted_at=instant.isoformat(),
                )
            )
            model=ReferenceNGramModel.train(
                tuple(corpus),
                order=order,
                model_id=f"skeleton-local-trained:{manifest.run_id}",
            )
            step=token_count
            checkpoint=TrainingCheckpoint(
                run_id=manifest.run_id,
                manifest_digest=manifest.digest,
                step=max(1,step),
                model_digest=model.model_digest,
                optimizer_digest=_digest_bytes(b"reference-ngram-count-estimator-v1"),
                rng_digest=_digest_bytes(str(manifest.seed).encode("ascii")),
                data_cursor_digest=actual_corpus_digest,
                worker_epoch=lease.epoch,
                created_at=instant.isoformat(),
            )
            checkpoint_digest=self.runs.checkpoint(checkpoint,lease)
            self.runs.record_telemetry(
                TrainingTelemetry(
                    run_id=manifest.run_id,
                    step=checkpoint.step,
                    metrics={"training_loss_proxy":0.0,"checkpoint_written":1.0},
                    emitted_at=instant.isoformat(),
                )
            )
            terminal=self.runs.complete(manifest.run_id)
            if terminal.digest!=checkpoint.digest:
                raise RuntimeError("training completion did not bind latest checkpoint")
        except Exception:
            if self.runs.state(manifest.run_id)=="running":
                self.runs.fail(manifest.run_id)
            raise

        artifact=LocalTrainingArtifact(
            run_id=manifest.run_id,
            run_manifest_digest=manifest.digest,
            dataset_digest=manifest.dataset_digest,
            model_id=model.model_id,
            model_digest=model.model_digest,
            checkpoint_digest=checkpoint_digest,
            corpus_digest=actual_corpus_digest,
            document_count=len(corpus),
        )
        return model,artifact

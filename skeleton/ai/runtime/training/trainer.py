"""Resumable, bounded reference-model training under the durable P3 authority."""

from __future__ import annotations

import hashlib
import sqlite3
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from skeleton.ai.runtime.inference import ReferenceNGramModel
from skeleton.ai.runtime.inference.local import _tokenize

from .control import (
    TrainingCheckpoint,
    TrainingRepository,
    TrainingRunManifest,
    TrainingStateError,
    TrainingTelemetry,
    WorkerLease,
    _digest,
)
from .data import DatasetRegistry

_ESTIMATOR = "reference-ngram-count-estimator-v1"
_BINDING_SCHEMA = "skeleton.reference_training_binding.v1"
_PAYLOAD_SCHEMA = "skeleton.reference_training_resume.v1"
_MAX_DOCUMENT_BYTES = 1024 * 1024
_MAX_CORPUS_BYTES = 64 * 1024 * 1024
_MAX_CHECKPOINT_DOCUMENTS = 4096


def _step_count(document: str) -> int:
    # Count the estimator's actual token observations, including document EOS.
    return len(_tokenize(document)) + 1


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
    """Train document batches, checkpoint full counts, and resume committed work."""

    def __init__(self, datasets: DatasetRegistry, runs: TrainingRepository) -> None:
        self.datasets = datasets
        self.runs = runs

    @staticmethod
    def _enforce_usage(manifest: TrainingRunManifest, usage: Mapping[str, int]) -> None:
        for budget_name, dimension in (
            ("max_steps", "steps"),
            ("max_documents", "documents"),
            ("max_corpus_bytes", "corpus_bytes"),
            ("max_batches", "batches"),
        ):
            limit = manifest.resource_budget.get(budget_name)
            actual = usage.get(dimension, 0)
            if limit is not None and actual > float(limit):
                raise TrainingStateError(
                    f"training budget exceeded: {budget_name} (actual={actual:g}, limit={float(limit):g})"
                )

    @classmethod
    def _enforce_execution_boundary(
        cls, manifest: TrainingRunManifest, corpus: Sequence[str]
    ) -> tuple[int, int]:
        if manifest.world_size != 1 or manifest.parallelism != "single":
            raise TrainingStateError(
                "reference local trainer only supports world_size=1 and parallelism=single"
            )
        sizes = [len(document.encode("utf-8")) for document in corpus]
        token_count = sum(_step_count(document) for document in corpus)
        corpus_bytes = sum(sizes) + len(corpus) - 1
        if max(sizes) > _MAX_DOCUMENT_BYTES:
            raise TrainingStateError("training document byte limit exceeded")
        if corpus_bytes > _MAX_CORPUS_BYTES:
            raise TrainingStateError("training corpus byte limit exceeded")
        cls._enforce_usage(
            manifest, {"steps": token_count, "documents": len(corpus), "corpus_bytes": corpus_bytes}
        )
        return token_count, corpus_bytes

    @staticmethod
    def _merge_models(
        previous: ReferenceNGramModel | None, batch: ReferenceNGramModel
    ) -> ReferenceNGramModel:
        tables: dict[tuple[str, ...], Counter[str]] = {}
        for model in (previous, batch):
            if model is None:
                continue
            for row in model.to_dict()["transitions"]:
                tables.setdefault(tuple(row["context"]), Counter()).update(row["counts"])
        return ReferenceNGramModel(order=batch.order, transitions=tables, model_id=batch.model_id)

    @staticmethod
    def _empty_model_digest(binding: Mapping[str, Any]) -> str:
        return _digest({"kind": "untrained_reference_ngram", "model_config": binding["model_config"]})

    def _restore(
        self,
        manifest: TrainingRunManifest,
        binding: Mapping[str, Any],
        checkpoint: TrainingCheckpoint,
        corpus: Sequence[str] | None = None,
    ) -> tuple[ReferenceNGramModel | None, dict[str, int]]:
        payload = self.runs.checkpoint_payload(checkpoint)
        try:
            if set(payload) != {"schema_version", "binding_digest", "cursor", "usage", "model", "finished"}:
                raise ValueError("unsupported payload fields")
            if payload["schema_version"] != _PAYLOAD_SCHEMA:
                raise ValueError("unsupported payload schema")
            if checkpoint.manifest_digest != manifest.digest:
                raise ValueError("manifest mismatch")
            cursor, usage = payload["cursor"], payload["usage"]
            if not isinstance(cursor, dict) or set(cursor) != {"document_index", "step", "corpus_bytes"}:
                raise ValueError("invalid cursor")
            if not isinstance(usage, dict) or set(usage) != {"steps", "documents", "corpus_bytes", "batches"}:
                raise ValueError("invalid usage")
            if any(
                isinstance(v, bool) or not isinstance(v, int) or v < 0
                for v in (*cursor.values(), *usage.values())
            ):
                raise ValueError("invalid cursor or usage values")
            index = cursor["document_index"]
            if not 0 <= index <= binding["document_count"]:
                raise ValueError("cursor outside corpus")
            if (
                usage["documents"] != index
                or usage["steps"] != cursor["step"]
                or usage["corpus_bytes"] != cursor["corpus_bytes"]
            ):
                raise ValueError("usage/cursor mismatch")
            if not 0 <= usage["batches"] <= index or (index > 0 and usage["batches"] == 0):
                raise ValueError("invalid cumulative batch count")
            if checkpoint.step != usage["steps"] or checkpoint.data_cursor_digest != _digest(cursor):
                raise ValueError("checkpoint/cursor mismatch")
            if payload["finished"] is not (index == binding["document_count"]):
                raise ValueError("terminal cursor mismatch")
            if corpus is not None:
                if usage["steps"] != sum(_step_count(item) for item in corpus[:index]):
                    raise ValueError("cursor token count mismatch")
                if usage["corpus_bytes"] != len("\n".join(corpus[:index]).encode("utf-8")):
                    raise ValueError("cursor corpus byte count mismatch")
            elif payload["finished"]:
                if (
                    usage["steps"] != binding["token_count"]
                    or usage["corpus_bytes"] != binding["corpus_bytes"]
                ):
                    raise ValueError("terminal usage mismatch")
            config = binding["model_config"]
            model = None if payload["model"] is None else ReferenceNGramModel.from_dict(payload["model"])
            if index == 0:
                if model is not None or checkpoint.model_digest != self._empty_model_digest(binding):
                    raise ValueError("invalid initial model")
            elif model is None or model.model_digest != checkpoint.model_digest:
                raise ValueError("checkpoint/model mismatch")
            if model is not None and (model.order != config["order"] or model.model_id != config["model_id"]):
                raise ValueError("model configuration mismatch")
            if checkpoint.optimizer_digest != _digest_bytes(
                _ESTIMATOR.encode()
            ) or checkpoint.rng_digest != _digest_bytes(str(manifest.seed).encode("ascii")):
                raise ValueError("estimator or seed mismatch")
            self._enforce_usage(manifest, usage)
        except (ValueError, TypeError, KeyError) as exc:
            raise TrainingStateError("invalid reference training resume payload") from exc
        return model, usage

    def _persist(
        self,
        manifest: TrainingRunManifest,
        binding: Mapping[str, Any],
        lease: WorkerLease,
        model: ReferenceNGramModel | None,
        usage: dict[str, int],
        instant: datetime,
    ) -> TrainingCheckpoint:
        cursor = {
            "document_index": usage["documents"],
            "step": usage["steps"],
            "corpus_bytes": usage["corpus_bytes"],
        }
        payload = {
            "schema_version": _PAYLOAD_SCHEMA,
            "binding_digest": _digest(binding),
            "cursor": cursor,
            "usage": usage,
            "model": None if model is None else model.to_dict(),
            "finished": usage["documents"] == binding["document_count"],
        }
        checkpoint = TrainingCheckpoint(
            run_id=manifest.run_id,
            manifest_digest=manifest.digest,
            step=usage["steps"],
            model_digest=self._empty_model_digest(binding) if model is None else model.model_digest,
            optimizer_digest=_digest_bytes(_ESTIMATOR.encode()),
            rng_digest=_digest_bytes(str(manifest.seed).encode("ascii")),
            data_cursor_digest=_digest(cursor),
            worker_epoch=lease.epoch,
            created_at=instant.isoformat(),
            payload_digest=_digest(payload),
        )
        with self.datasets.training_authority(manifest.dataset_digest, binding["dataset_authority_epoch"]):
            self.runs.checkpoint(checkpoint, lease, payload=payload)
        return checkpoint

    @staticmethod
    def _artifact(
        manifest: TrainingRunManifest,
        binding: Mapping[str, Any],
        model: ReferenceNGramModel,
        checkpoint: TrainingCheckpoint,
    ) -> LocalTrainingArtifact:
        return LocalTrainingArtifact(
            run_id=manifest.run_id,
            run_manifest_digest=manifest.digest,
            dataset_digest=manifest.dataset_digest,
            model_id=model.model_id,
            model_digest=model.model_digest,
            checkpoint_digest=checkpoint.digest,
            corpus_digest=binding["corpus_digest"],
            document_count=binding["document_count"],
        )

    def load_artifact(self, run_id: str) -> tuple[ReferenceNGramModel, LocalTrainingArtifact]:
        """Reload a completed learned model after restart without requiring corpus text."""
        manifest = self.runs.manifest(run_id)
        binding = self.runs.execution_binding(run_id)
        checkpoint = self.runs.latest_checkpoint(run_id)
        if self.runs.state(run_id) != "completed" or binding is None or checkpoint is None:
            raise TrainingStateError("model artifact requires a completed payload-backed training run")
        model, usage = self._restore(manifest, binding, checkpoint)
        if model is None or usage["documents"] != binding["document_count"]:
            raise TrainingStateError("completed model artifact is incomplete")
        return model, self._artifact(manifest, binding, model, checkpoint)

    def train(
        self,
        manifest: TrainingRunManifest,
        corpus: Sequence[str],
        *,
        split_name: str = "train",
        order: int = 2,
        worker_id: str = "local-trainer",
        now: datetime | None = None,
        checkpoint_every_documents: int = 16,
    ) -> tuple[ReferenceNGramModel, LocalTrainingArtifact]:
        instant = now or datetime.now(UTC)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        if isinstance(order, bool) or not isinstance(order, int) or not 1 <= order <= 8:
            raise ValueError("order must be an integer in [1, 8]")
        if "order" in manifest.hyperparameters and manifest.hyperparameters["order"] != order:
            raise TrainingStateError("requested order conflicts with immutable training manifest")
        if (
            isinstance(checkpoint_every_documents, bool)
            or not isinstance(checkpoint_every_documents, int)
            or not 1 <= checkpoint_every_documents <= _MAX_CHECKPOINT_DOCUMENTS
        ):
            raise ValueError("checkpoint_every_documents must be an integer in [1, 4096]")
        documents = tuple(corpus)
        actual_corpus_digest = corpus_digest(documents)
        dataset = self.datasets.require_training_ready(manifest.dataset_digest)
        split = next((item for item in dataset.splits if item.name == split_name), None)
        if split is None:
            raise ValueError(f"dataset split not found: {split_name}")
        if split.digest != actual_corpus_digest:
            raise ValueError("training corpus bytes do not match registered split digest")
        if split.record_count != len(documents):
            raise ValueError("training document count does not match registered split")
        token_count, corpus_bytes = self._enforce_execution_boundary(manifest, documents)
        self.datasets.validate_training_corpus(manifest.dataset_digest, documents, split_name=split_name)
        authority_epoch = self.datasets.dataset_authority_epoch(manifest.dataset_digest)
        self.datasets.assert_dataset_authority(manifest.dataset_digest, authority_epoch)
        binding = {
            "schema_version": _BINDING_SCHEMA,
            "manifest_digest": manifest.digest,
            "dataset_digest": manifest.dataset_digest,
            "dataset_authority_epoch": authority_epoch,
            "split_name": split_name,
            "split_digest": split.digest,
            "corpus_digest": actual_corpus_digest,
            "document_sequence_digest": _digest(documents),
            "document_count": len(documents),
            "token_count": token_count,
            "corpus_bytes": corpus_bytes,
            "model_config": {
                "kind": "reference_ngram",
                "model_id": f"skeleton-local-trained:{manifest.run_id}",
                "order": order,
                "estimator": _ESTIMATOR,
            },
        }
        self.runs.register_run(manifest, self.datasets, created_at=instant)
        self.runs.bind_execution(manifest.run_id, binding)
        state = self.runs.state(manifest.run_id)
        checkpoint = self.runs.latest_checkpoint(manifest.run_id)
        model = None
        usage = {"steps": 0, "documents": 0, "corpus_bytes": 0, "batches": 0}
        if checkpoint is not None:
            model, usage = self._restore(manifest, binding, checkpoint, documents)
        if state == "completed":
            return self.load_artifact(manifest.run_id)
        if state in {"running", "failed"}:
            checkpoint = self.runs.recover(manifest.run_id, allow_empty=True)
            if checkpoint is not None:
                model, usage = self._restore(manifest, binding, checkpoint, documents)
            state = "recovering"
        if state not in {"registered", "recovering"}:
            raise TrainingStateError(f"training run cannot execute from state {state}")
        self.runs.start(manifest.run_id)
        lease = self.runs.lease_worker(manifest.run_id, worker_id, issued_at=instant)
        try:
            if checkpoint is None:
                checkpoint = self._persist(manifest, binding, lease, None, usage, instant)
            self.runs.record_telemetry(
                TrainingTelemetry(
                    manifest.run_id,
                    usage["steps"],
                    {"resumed_documents": float(usage["documents"]), "world_size": 1.0},
                    instant.isoformat(),
                ),
                lease,
            )
            while usage["documents"] < len(documents):
                self.runs.assert_worker_current(lease)
                self.datasets.assert_dataset_authority(manifest.dataset_digest, authority_epoch)
                start = usage["documents"]
                end = min(len(documents), start + checkpoint_every_documents)
                batch = documents[start:end]
                next_usage = {
                    "steps": usage["steps"] + sum(_step_count(item) for item in batch),
                    "documents": end,
                    "corpus_bytes": usage["corpus_bytes"]
                    + sum(len(item.encode("utf-8")) for item in batch)
                    + len(batch)
                    - (1 if start == 0 else 0),
                    "batches": usage["batches"] + 1,
                }
                self._enforce_usage(manifest, next_usage)
                batch_model = ReferenceNGramModel.train(
                    batch, order=order, model_id=binding["model_config"]["model_id"]
                )
                model = self._merge_models(model, batch_model)
                checkpoint = self._persist(manifest, binding, lease, model, next_usage, instant)
                usage = next_usage
                self.runs.record_telemetry(
                    TrainingTelemetry(
                        manifest.run_id,
                        checkpoint.step,
                        {
                            "checkpoint_written": 1.0,
                            "documents": float(usage["documents"]),
                            "batches": float(usage["batches"]),
                        },
                        instant.isoformat(),
                    ),
                    lease,
                )
            with self.datasets.training_authority(manifest.dataset_digest, authority_epoch):
                terminal = self.runs.complete(manifest.run_id, lease)
            if terminal.digest != checkpoint.digest:
                raise TrainingStateError("training completion did not bind latest checkpoint")
        except Exception:
            try:
                self.runs.fail(manifest.run_id, lease)
            except (TrainingStateError, sqlite3.Error):
                # A replacement worker owns the run; this worker cannot change its state.
                pass
            raise
        if model is None:
            raise TrainingStateError("training produced no model")
        return model, self._artifact(manifest, binding, model, checkpoint)

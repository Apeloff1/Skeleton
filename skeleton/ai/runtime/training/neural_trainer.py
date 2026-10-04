"""Real resumable NumPy neural SGD under the existing native training authority."""

from __future__ import annotations

import math
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from skeleton.ai.runtime.inference.neural import (
    NeuralLMConfig,
    NeuralLMError,
    NumpyRecurrentLM,
)

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
from .trainer import LocalTrainingArtifact, corpus_digest

_ALGORITHM = "numpy-recurrent-byte-sgd-v1"
_BINDING_SCHEMA = "skeleton.neural_training_binding.v1"
_PAYLOAD_SCHEMA = "skeleton.neural_training_resume.v1"
_MAX_HIDDEN_SIZE = 128
_MAX_DOCUMENT_BYTES = 4096
_MAX_CORPUS_BYTES = 1024 * 1024
_MAX_EPOCHS = 1024
_MAX_TARGETS = 16 * 1024 * 1024
_MAX_UPDATES = 65536


@dataclass(frozen=True, slots=True)
class NeuralTrainingArtifact(LocalTrainingArtifact):
    initial_model_digest: str
    initial_loss: float
    final_loss: float
    epochs: int
    update_count: int
    token_count: int
    training_bytes: int
    training_receipt_digest: str


class NeuralLocalTrainer:
    """Checkpoint every real SGD document update with its exact epoch cursor."""

    def __init__(self, datasets: DatasetRegistry, runs: TrainingRepository) -> None:
        self.datasets = datasets
        self.runs = runs

    @staticmethod
    def initialize_model(run_id: str, *, hidden_size: int = 24, seed: int = 0) -> NumpyRecurrentLM:
        if (
            isinstance(hidden_size, bool)
            or not isinstance(hidden_size, int)
            or not 4 <= hidden_size <= _MAX_HIDDEN_SIZE
        ):
            raise TrainingStateError("native neural hidden_size must be in [4, 128]")
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must be non-empty")
        return NumpyRecurrentLM(
            model_id=f"skeleton-local-neural:{run_id}",
            config=NeuralLMConfig(hidden_size=hidden_size, seed=seed),
        )

    @staticmethod
    def _optimizer(config: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "algorithm": _ALGORITHM,
            "learning_rate": config["learning_rate"],
            "gradient_clip": config["gradient_clip"],
            "slots": {},
        }

    @staticmethod
    def _usage(
        binding: Mapping[str, Any], epoch: int, document_index: int, documents: Sequence[str] | None = None
    ) -> dict[str, int]:
        updates = epoch * binding["document_count"] + document_index
        if document_index and documents is None:
            raise TrainingStateError("partial neural cursor requires exact corpus for resume")
        prefix_bytes = (
            0 if documents is None else sum(len(item.encode("utf-8")) for item in documents[:document_index])
        )
        return {
            "steps": epoch * binding["targets_per_epoch"] + prefix_bytes + document_index,
            "documents": updates,
            "training_bytes": epoch * binding["document_bytes"] + prefix_bytes,
            "epochs": epoch,
        }

    @staticmethod
    def _enforce_usage(manifest: TrainingRunManifest, usage: Mapping[str, int], *, corpus_bytes: int) -> None:
        if usage["steps"] > _MAX_TARGETS or usage["documents"] > _MAX_UPDATES:
            raise TrainingStateError("native neural hard execution budget exceeded")
        for name, actual in (
            ("max_steps", usage["steps"]),
            ("max_tokens", usage["steps"]),
            ("max_documents", usage["documents"]),
            ("max_updates", usage["documents"]),
            ("max_training_bytes", usage["training_bytes"]),
            ("max_epochs", usage["epochs"]),
            ("max_corpus_bytes", corpus_bytes),
        ):
            limit = manifest.resource_budget.get(name)
            if limit is not None and actual > limit:
                raise TrainingStateError(
                    f"neural training budget exceeded: {name} (actual={actual}, limit={limit:g})"
                )

    def _authority(self, binding: Mapping[str, Any]) -> None:
        self.datasets.assert_dataset_authority(binding["dataset_digest"], binding["dataset_authority_epoch"])

    def _persist(
        self,
        manifest: TrainingRunManifest,
        binding: Mapping[str, Any],
        lease: WorkerLease,
        model: NumpyRecurrentLM,
        cursor: dict[str, int],
        usage: dict[str, int],
        initial_loss: float,
        final_loss: float | None,
        instant: datetime,
    ) -> TrainingCheckpoint:
        with self.datasets.training_authority(binding["dataset_digest"], binding["dataset_authority_epoch"]):
            self._authority(binding)
            optimizer = self._optimizer(binding["training_config"])
            payload = {
                "schema_version": _PAYLOAD_SCHEMA,
                "binding_digest": _digest(binding),
                "cursor": cursor,
                "usage": usage,
                "optimizer": optimizer,
                "model": model.to_dict(),
                "initial_loss": initial_loss,
                "final_loss": final_loss,
                "finished": cursor["epoch"] == binding["training_config"]["epochs"],
            }
            checkpoint = TrainingCheckpoint(
                run_id=manifest.run_id,
                manifest_digest=manifest.digest,
                step=usage["steps"],
                model_digest=model.model_digest,
                optimizer_digest=_digest(optimizer),
                rng_digest=_digest({"seed": manifest.seed, "draws_after_initialization": 0}),
                data_cursor_digest=_digest(cursor),
                worker_epoch=lease.epoch,
                created_at=instant.isoformat(),
                payload_digest=_digest(payload),
            )
            self.runs.checkpoint(checkpoint, lease, payload=payload)
            return checkpoint

    def _restore(
        self,
        manifest: TrainingRunManifest,
        binding: Mapping[str, Any],
        checkpoint: TrainingCheckpoint,
        documents: Sequence[str] | None = None,
    ) -> tuple[NumpyRecurrentLM, dict[str, int], dict[str, int], float, float | None]:
        self._authority(binding)
        payload = self.runs.checkpoint_payload(checkpoint)
        try:
            if (
                set(payload)
                != {
                    "schema_version",
                    "binding_digest",
                    "cursor",
                    "usage",
                    "optimizer",
                    "model",
                    "initial_loss",
                    "final_loss",
                    "finished",
                }
                or payload["schema_version"] != _PAYLOAD_SCHEMA
            ):
                raise ValueError("unsupported neural resume schema")
            config = binding["training_config"]
            if (
                binding["schema_version"] != _BINDING_SCHEMA
                or binding["manifest_digest"] != manifest.digest
                or binding["initial_model_digest"] != manifest.base_model_digest
            ):
                raise ValueError("binding manifest/base mismatch")
            if (
                checkpoint.manifest_digest != manifest.digest
                or payload["optimizer"] != self._optimizer(config)
                or checkpoint.optimizer_digest != _digest(payload["optimizer"])
            ):
                raise ValueError("optimizer/manifest mismatch")
            if checkpoint.rng_digest != _digest({"seed": manifest.seed, "draws_after_initialization": 0}):
                raise ValueError("seed mismatch")
            cursor, usage = payload["cursor"], payload["usage"]
            if not isinstance(cursor, dict) or set(cursor) != {
                "epoch",
                "document_index",
                "update_count",
                "step",
            }:
                raise ValueError("invalid neural cursor")
            if not isinstance(usage, dict) or set(usage) != {
                "steps",
                "documents",
                "training_bytes",
                "epochs",
            }:
                raise ValueError("invalid neural usage")
            if any(
                isinstance(v, bool) or not isinstance(v, int) or v < 0
                for v in (*cursor.values(), *usage.values())
            ):
                raise ValueError("invalid cursor/usage values")
            epoch, index = cursor["epoch"], cursor["document_index"]
            if (
                epoch > config["epochs"]
                or not 0 <= index < binding["document_count"]
                or (epoch == config["epochs"] and index)
            ):
                raise ValueError("cursor outside epoch/document bounds")
            expected_usage = self._usage(binding, epoch, index, documents)
            if (
                usage != expected_usage
                or cursor["update_count"] != usage["documents"]
                or cursor["step"] != usage["steps"]
            ):
                raise ValueError("cumulative usage mismatch")
            if checkpoint.step != usage["steps"] or checkpoint.data_cursor_digest != _digest(cursor):
                raise ValueError("checkpoint/cursor mismatch")
            if payload["finished"] is not (epoch == config["epochs"]):
                raise ValueError("terminal cursor mismatch")
            initial_loss, final_loss = payload["initial_loss"], payload["final_loss"]
            if (
                isinstance(initial_loss, bool)
                or not isinstance(initial_loss, (int, float))
                or not math.isfinite(initial_loss)
                or initial_loss < 0
            ):
                raise ValueError("invalid initial loss")
            if payload["finished"]:
                if (
                    isinstance(final_loss, bool)
                    or not isinstance(final_loss, (int, float))
                    or not math.isfinite(final_loss)
                    or final_loss < 0
                ):
                    raise ValueError("invalid final loss")
            elif final_loss is not None:
                raise ValueError("nonterminal final loss")
            model = NumpyRecurrentLM.from_dict(payload["model"])
            if (
                model.model_id != config["model_id"]
                or model.config.as_dict()
                != NeuralLMConfig(
                    hidden_size=config["hidden_size"], seed=config["seed"], dtype=config["dtype"]
                ).as_dict()
                or model.model_digest != checkpoint.model_digest
            ):
                raise ValueError("neural model identity mismatch")
            if cursor["update_count"] == 0 and model.model_digest != manifest.base_model_digest:
                raise ValueError("initial model mismatch")
            self._enforce_usage(manifest, usage, corpus_bytes=binding["corpus_bytes"])
        except (ValueError, TypeError, KeyError, NeuralLMError) as exc:
            raise TrainingStateError("invalid neural training resume payload") from exc
        return model, cursor, usage, float(initial_loss), None if final_loss is None else float(final_loss)

    @staticmethod
    def _artifact(
        manifest: TrainingRunManifest,
        binding: Mapping[str, Any],
        checkpoint: TrainingCheckpoint,
        model: NumpyRecurrentLM,
        initial_loss: float,
        final_loss: float,
        usage: Mapping[str, int],
    ) -> NeuralTrainingArtifact:
        receipt = {
            "schema_version": "skeleton.native_neural_training_receipt.v1",
            "binding_digest": _digest(binding),
            "initial_model_digest": binding["initial_model_digest"],
            "model_digest": model.model_digest,
            "initial_loss": initial_loss,
            "final_loss": final_loss,
            "usage": dict(usage),
        }
        return NeuralTrainingArtifact(
            run_id=manifest.run_id,
            run_manifest_digest=manifest.digest,
            dataset_digest=manifest.dataset_digest,
            model_id=model.model_id,
            model_digest=model.model_digest,
            checkpoint_digest=checkpoint.digest,
            corpus_digest=binding["corpus_digest"],
            document_count=binding["document_count"],
            initial_model_digest=binding["initial_model_digest"],
            initial_loss=initial_loss,
            final_loss=final_loss,
            epochs=binding["training_config"]["epochs"],
            update_count=usage["documents"],
            token_count=usage["steps"],
            training_bytes=usage["training_bytes"],
            training_receipt_digest=_digest(receipt),
        )

    def load_artifact(self, run_id: str) -> tuple[NumpyRecurrentLM, NeuralTrainingArtifact]:
        manifest = self.runs.manifest(run_id)
        binding = self.runs.execution_binding(run_id)
        checkpoint = self.runs.latest_checkpoint(run_id)
        if self.runs.state(run_id) != "completed" or binding is None or checkpoint is None:
            raise TrainingStateError("neural artifact requires a completed payload-backed training run")
        model, cursor, usage, initial_loss, final_loss = self._restore(manifest, binding, checkpoint)
        if final_loss is None or cursor["epoch"] != binding["training_config"]["epochs"]:
            raise TrainingStateError("completed neural artifact is incomplete")
        return model, self._artifact(manifest, binding, checkpoint, model, initial_loss, final_loss, usage)

    def train(
        self,
        manifest: TrainingRunManifest,
        corpus: Sequence[str],
        *,
        split_name: str = "train",
        hidden_size: int = 24,
        epochs: int = 8,
        learning_rate: float = 0.05,
        gradient_clip: float = 1.0,
        worker_id: str = "local-neural-trainer",
        now: datetime | None = None,
    ) -> tuple[NumpyRecurrentLM, NeuralTrainingArtifact]:
        instant = now or datetime.now(UTC)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        if manifest.world_size != 1 or manifest.parallelism != "single":
            raise TrainingStateError("neural local trainer supports one worker and single parallelism")
        if isinstance(epochs, bool) or not isinstance(epochs, int) or not 1 <= epochs <= _MAX_EPOCHS:
            raise TrainingStateError("neural epochs must be in [1, 1024]")
        for name, value, maximum in (
            ("learning_rate", learning_rate, 10.0),
            ("gradient_clip", gradient_clip, 1000.0),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not 0 < value <= maximum
            ):
                raise TrainingStateError(f"invalid neural {name}")
        config = {
            "algorithm": _ALGORITHM,
            "model_id": f"skeleton-local-neural:{manifest.run_id}",
            "hidden_size": hidden_size,
            "seed": manifest.seed,
            "dtype": "float64",
            "epochs": epochs,
            "learning_rate": float(learning_rate),
            "gradient_clip": float(gradient_clip),
        }
        for name in ("hidden_size", "epochs", "learning_rate", "gradient_clip", "dtype"):
            if name in manifest.hyperparameters and manifest.hyperparameters[name] != config[name]:
                raise TrainingStateError(f"neural {name} conflicts with immutable manifest")
        documents = tuple(corpus)
        digest = corpus_digest(documents)
        dataset = self.datasets.require_training_ready(manifest.dataset_digest)
        self.datasets.validate_training_corpus(manifest.dataset_digest, documents, split_name=split_name)
        split = next((item for item in dataset.splits if item.name == split_name), None)
        if split is None or split.digest != digest or split.record_count != len(documents):
            raise TrainingStateError("neural corpus does not match registered dataset split")
        sizes = [len(item.encode("utf-8")) for item in documents]
        corpus_bytes = sum(sizes) + len(documents) - 1
        if max(sizes) > _MAX_DOCUMENT_BYTES or corpus_bytes > _MAX_CORPUS_BYTES:
            raise TrainingStateError("neural document/corpus byte limit exceeded")
        binding = {
            "schema_version": _BINDING_SCHEMA,
            "manifest_digest": manifest.digest,
            "dataset_digest": manifest.dataset_digest,
            "dataset_authority_epoch": self.datasets.dataset_authority_epoch(manifest.dataset_digest),
            "split_name": split_name,
            "split_digest": split.digest,
            "corpus_digest": digest,
            "document_sequence_digest": _digest(documents),
            "document_count": len(documents),
            "corpus_bytes": corpus_bytes,
            "document_bytes": sum(sizes),
            "targets_per_epoch": sum(sizes) + len(documents),
            "training_config": config,
            "initial_model_digest": manifest.base_model_digest,
        }
        self._enforce_usage(manifest, self._usage(binding, epochs, 0), corpus_bytes=corpus_bytes)
        model = self.initialize_model(manifest.run_id, hidden_size=hidden_size, seed=manifest.seed)
        if model.model_digest != manifest.base_model_digest:
            raise TrainingStateError("neural initialized base model digest does not match manifest")
        self.runs.register_run(manifest, self.datasets, created_at=instant)
        self.runs.bind_execution(manifest.run_id, binding)
        state = self.runs.state(manifest.run_id)
        checkpoint = self.runs.latest_checkpoint(manifest.run_id)
        cursor = {"epoch": 0, "document_index": 0, "update_count": 0, "step": 0}
        usage = self._usage(binding, 0, 0)
        initial_loss, final_loss = None, None
        if checkpoint is not None:
            model, cursor, usage, initial_loss, final_loss = self._restore(
                manifest, binding, checkpoint, documents
            )
        if state == "completed":
            return self.load_artifact(manifest.run_id)
        if state in {"running", "failed"}:
            checkpoint = self.runs.recover(manifest.run_id, allow_empty=True)
            if checkpoint is not None:
                model, cursor, usage, initial_loss, final_loss = self._restore(
                    manifest, binding, checkpoint, documents
                )
            state = "recovering"
        if state not in {"registered", "recovering"}:
            raise TrainingStateError(f"neural run cannot execute from {state}")
        self.runs.start(manifest.run_id)
        lease = self.runs.lease_worker(manifest.run_id, worker_id, issued_at=instant)
        try:
            if checkpoint is None:
                self._authority(binding)
                initial_loss = model.loss(documents)
                if not math.isfinite(initial_loss):
                    raise TrainingStateError("nonfinite initial neural loss")
                checkpoint = self._persist(
                    manifest, binding, lease, model, cursor, usage, initial_loss, None, instant
                )
            while cursor["epoch"] < epochs:
                self.runs.assert_worker_current(lease)
                self._authority(binding)
                index = cursor["document_index"]
                epoch, next_index = cursor["epoch"], index + 1
                if next_index == len(documents):
                    epoch, next_index = epoch + 1, 0
                next_usage = self._usage(binding, epoch, next_index, documents)
                self._enforce_usage(manifest, next_usage, corpus_bytes=corpus_bytes)
                observed = model.train_document(
                    documents[index], learning_rate=learning_rate, gradient_clip=gradient_clip
                )
                if observed != sizes[index] + 1:
                    raise TrainingStateError("neural update target usage drift")
                next_cursor = {
                    "epoch": epoch,
                    "document_index": next_index,
                    "update_count": next_usage["documents"],
                    "step": next_usage["steps"],
                }
                if epoch == epochs:
                    final_loss = model.loss(documents)
                    if not math.isfinite(final_loss):
                        raise TrainingStateError("nonfinite final neural loss")
                checkpoint = self._persist(
                    manifest,
                    binding,
                    lease,
                    model,
                    next_cursor,
                    next_usage,
                    initial_loss,
                    final_loss,
                    instant,
                )
                cursor, usage = next_cursor, next_usage
                self.runs.record_telemetry(
                    TrainingTelemetry(
                        manifest.run_id,
                        checkpoint.step,
                        {
                            "sgd_updates": float(usage["documents"]),
                            "epoch": float(cursor["epoch"]),
                            "checkpoint_written": 1.0,
                        },
                        instant.isoformat(),
                    ),
                    lease,
                )
            with self.datasets.training_authority(
                binding["dataset_digest"], binding["dataset_authority_epoch"]
            ):
                terminal = self.runs.complete(manifest.run_id, lease)
            if terminal.digest != checkpoint.digest:
                raise TrainingStateError("neural terminal checkpoint identity drift")
        except Exception:
            try:
                self.runs.fail(manifest.run_id, lease)
            except (TrainingStateError, sqlite3.Error):
                pass
            raise
        if initial_loss is None or final_loss is None:
            raise TrainingStateError("neural training loss evidence is incomplete")
        return model, self._artifact(manifest, binding, checkpoint, model, initial_loss, final_loss, usage)
